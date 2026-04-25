"""
WAF Classifier — SSO / OIDC authentication middleware.

Activated only when AUTH_MODE=oidc in .env.  When inactive (AUTH_MODE=none,
the default), none of this code touches any request.

Supports any OIDC-compliant IdP:
  • Okta
  • Azure AD / Entra ID
  • Ping Identity / PingFederate
  • Keycloak
  • Google Workspace
  • Any IdP that exposes /.well-known/openid-configuration

Required .env keys (AUTH_MODE=oidc):
  OIDC_DISCOVERY_URL   – e.g. https://login.microsoftonline.com/{tenant}/v2.0
  OIDC_CLIENT_ID       – App/client ID registered with the IdP
  OIDC_CLIENT_SECRET   – Client secret
  OIDC_REDIRECT_URI    – Full callback URL, e.g. https://app.example.com/auth/callback
  SESSION_SECRET_KEY   – A long random string for Flask session signing
                         (overrides the default os.urandom key so sessions
                          survive app restarts in multi-worker deployments)

Optional:
  OIDC_SCOPES          – Space-separated (default: "openid email profile")
  OIDC_AUDIENCE        – Required by some IdPs (e.g. Okta resource server)
"""

import os
import json
import hashlib
import secrets
import time
import logging

logger = logging.getLogger(__name__)

# ── Runtime flag — read once at import ────────────────────────────────
AUTH_MODE = os.environ.get("AUTH_MODE", "none").lower().strip()
SSO_ENABLED = (AUTH_MODE == "oidc")

# ── Paths that are always public (no auth required) ───────────────────
_PUBLIC_PREFIXES = ("/auth/", "/static/", "/favicon")

# ── OIDC metadata cache ───────────────────────────────────────────────
_oidc_meta = {}
_meta_fetched_at = 0
_META_TTL = 3600  # re-fetch discovery doc after 1 hour


def _get_oidc_meta():
    """Fetch (and cache) the OIDC discovery document."""
    global _oidc_meta, _meta_fetched_at
    if _oidc_meta and (time.time() - _meta_fetched_at) < _META_TTL:
        return _oidc_meta
    import requests
    base = os.environ.get("OIDC_DISCOVERY_URL", "").rstrip("/")
    well_known = base if base.endswith("openid-configuration") else f"{base}/.well-known/openid-configuration"
    resp = requests.get(well_known, timeout=10)
    resp.raise_for_status()
    _oidc_meta = resp.json()
    _meta_fetched_at = time.time()
    logger.info("[SSO] Loaded OIDC discovery from %s", well_known)
    return _oidc_meta


def _cfg(key, required=True):
    val = os.environ.get(key, "").strip()
    if required and not val:
        raise RuntimeError(f"[SSO] Missing required env var: {key}")
    return val


def init_sso(app):
    """
    Register SSO routes and before_request guard on the Flask app.
    No-op when AUTH_MODE != 'oidc'.
    """
    if not SSO_ENABLED:
        logger.info("[SSO] AUTH_MODE=%s — SSO disabled, all routes public", AUTH_MODE)
        return

    # Validate config eagerly so the error is obvious at startup
    try:
        _cfg("OIDC_DISCOVERY_URL")
        _cfg("OIDC_CLIENT_ID")
        _cfg("OIDC_CLIENT_SECRET")
        _cfg("OIDC_REDIRECT_URI")
    except RuntimeError as e:
        logger.error(str(e))
        raise

    # Stable secret key so sessions survive restarts / gunicorn workers
    session_key = os.environ.get("SESSION_SECRET_KEY", "").strip()
    if session_key:
        app.secret_key = session_key
        logger.info("[SSO] Using SESSION_SECRET_KEY for stable session signing")
    else:
        logger.warning(
            "[SSO] SESSION_SECRET_KEY not set — sessions will be invalidated on restart. "
            "Set SESSION_SECRET_KEY in .env for production."
        )

    from flask import request, redirect, session, url_for
    import urllib.parse

    # ── Auth routes ───────────────────────────────────────────────────

    @app.route("/auth/login")
    def sso_login():
        meta = _get_oidc_meta()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        session["oidc_state"] = state
        session["oidc_nonce"] = nonce
        session["next"] = request.args.get("next", "/")
        scopes = os.environ.get("OIDC_SCOPES", "openid email profile")
        params = {
            "response_type": "code",
            "client_id": _cfg("OIDC_CLIENT_ID"),
            "redirect_uri": _cfg("OIDC_REDIRECT_URI"),
            "scope": scopes,
            "state": state,
            "nonce": nonce,
        }
        aud = os.environ.get("OIDC_AUDIENCE", "").strip()
        if aud:
            params["audience"] = aud
        auth_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
        return redirect(auth_url)

    @app.route("/auth/callback")
    def sso_callback():
        import requests as _req
        meta = _get_oidc_meta()
        error = request.args.get("error")
        if error:
            desc = request.args.get("error_description", "")
            logger.warning("[SSO] IdP returned error: %s — %s", error, desc)
            return f"<h2>Login failed</h2><p>{error}: {desc}</p>", 403

        state = request.args.get("state", "")
        if state != session.pop("oidc_state", None):
            return "<h2>Login failed</h2><p>State mismatch (CSRF check).</p>", 403

        code = request.args.get("code")
        if not code:
            return "<h2>Login failed</h2><p>No authorization code.</p>", 400

        # Exchange code for tokens
        token_resp = _req.post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _cfg("OIDC_REDIRECT_URI"),
                "client_id": _cfg("OIDC_CLIENT_ID"),
                "client_secret": _cfg("OIDC_CLIENT_SECRET"),
            },
            timeout=15,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Decode id_token claims (no sig verification — IdP already verified)
        id_token = tokens.get("id_token", "")
        claims = _decode_jwt_payload(id_token)

        # Verify nonce to prevent replay
        if claims.get("nonce") != session.pop("oidc_nonce", None):
            return "<h2>Login failed</h2><p>Nonce mismatch.</p>", 403

        session["user"] = {
            "sub":   claims.get("sub", ""),
            "email": claims.get("email", claims.get("preferred_username", "")),
            "name":  claims.get("name", claims.get("email", "User")),
        }
        session["access_token"] = tokens.get("access_token", "")
        logger.info("[SSO] Login: %s", session["user"].get("email", "?"))

        next_url = session.pop("next", "/")
        return redirect(next_url)

    @app.route("/auth/logout")
    def sso_logout():
        user = session.pop("user", None)
        session.pop("access_token", None)
        if user:
            logger.info("[SSO] Logout: %s", user.get("email", "?"))
        # Attempt IdP-side logout if end_session_endpoint is published
        meta = {}
        try:
            meta = _get_oidc_meta()
        except Exception:
            pass
        end_session = meta.get("end_session_endpoint", "")
        if end_session:
            import urllib.parse
            params = {"post_logout_redirect_uri": _cfg("OIDC_REDIRECT_URI", required=False) or "/"}
            return redirect(end_session + "?" + urllib.parse.urlencode(params))
        return redirect("/")

    # ── before_request guard ──────────────────────────────────────────

    @app.before_request
    def require_login():
        path = request.path
        # Always allow public paths
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return
        # Already authenticated
        if session.get("user"):
            return
        # Redirect to IdP login, preserving the intended destination
        return redirect(f"/auth/login?next={urllib.parse.quote(request.url, safe='')}")

    logger.info("[SSO] OIDC authentication enabled — IdP: %s",
                os.environ.get("OIDC_DISCOVERY_URL", "(not set)"))


def _decode_jwt_payload(token: str) -> dict:
    """Base64-decode the JWT payload section without verifying the signature.
    Signature verification is not needed here — the token was just issued by
    the IdP over a TLS-protected token endpoint we called ourselves."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        # Add padding
        payload += "=" * (-len(payload) % 4)
        import base64
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.warning("[SSO] Could not decode id_token payload: %s", e)
        return {}


def current_user():
    """Return the logged-in user dict (or None if SSO is disabled / not logged in)."""
    if not SSO_ENABLED:
        return None
    try:
        from flask import session
        return session.get("user")
    except RuntimeError:
        return None
