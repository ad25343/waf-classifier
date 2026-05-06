"""
WAF Classifier — Page-serving routes.
Reads static HTML files and injects APP_ROOT so all fetch() calls and
<a href="/..."> links work correctly when the app is deployed under a
sub-path (e.g. /h591-wafui).  Set APPLICATION_ROOT in .env to activate;
leave it empty for root-path / local-dev use (zero-change behaviour).
"""

import os
from flask import Blueprint, Response, redirect
from config import APPLICATION_ROOT

pages_bp = Blueprint("pages_bp", __name__)

# Absolute path to the static/ directory
_STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

# JS snippet injected into <head> of every page.
# When APP_ROOT is empty the IIFE exits immediately — no runtime cost.
_APP_ROOT_SCRIPT = """\
<script>
window.APP_ROOT = "{prefix}";
(function() {{
  if (!window.APP_ROOT) return;
  /* Patch fetch so every root-relative URL is prefixed automatically */
  var _f = window.fetch.bind(window);
  window.fetch = function(url, opts) {{
    if (typeof url === 'string' && url.startsWith('/') &&
        !url.startsWith(window.APP_ROOT + '/'))
      url = window.APP_ROOT + url;
    return _f(url, opts);
  }};
  /* Patch <a href="/..."> links once the DOM is ready */
  document.addEventListener('DOMContentLoaded', function() {{
    document.querySelectorAll('a[href^="/"]').forEach(function(a) {{
      var h = a.getAttribute('href');
      if (!h.startsWith(window.APP_ROOT)) a.href = window.APP_ROOT + h;
    }});
  }});
}})();
</script>
"""


# Shared helper script tag — loaded on every page so any view can call
# window.openDisputeModal(...). The src is APP_ROOT-aware via the Flask
# /static mount; the APP_ROOT fetch shim above will rewrite the request.
_DISPUTE_MODAL_TAG = '<script src="{prefix}/static/dispute-modal.js"></script>'


def _serve(filename):
    """Read a static HTML file, inject the APP_ROOT script, and return it."""
    with open(os.path.join(_STATIC, filename), "r", encoding="utf-8") as fh:
        html = fh.read()
    script = _APP_ROOT_SCRIPT.format(prefix=APPLICATION_ROOT)
    dispute_tag = _DISPUTE_MODAL_TAG.format(prefix=APPLICATION_ROOT)
    # Inject right after <head> so APP_ROOT is defined before any page script
    html = html.replace("<head>", "<head>\n" + script + "\n" + dispute_tag, 1)
    return Response(html, mimetype="text/html")


# ── Routes ────────────────────────────────────────────────────────────

@pages_bp.route("/")
def home():
    return _serve("home.html")


@pages_bp.route("/classify")
def classify_page():
    return _serve("index.html")


@pages_bp.route("/dashboard")
def dashboard():
    return redirect(APPLICATION_ROOT + "/history")


@pages_bp.route("/history")
def history():
    return _serve("history.html")


@pages_bp.route("/waf-reference")
def waf_reference():
    return _serve("waf-reference.html")


@pages_bp.route("/lineage")
def lineage_page():
    return _serve("lineage.html")


@pages_bp.route("/settings")
def settings_page():
    return _serve("settings.html")


@pages_bp.route("/teams")
def teams_page():
    return _serve("teams.html")


@pages_bp.route("/merge")
def merge_page():
    return _serve("merge.html")


@pages_bp.route("/disputes")
def disputes_page():
    return _serve("disputes.html")


@pages_bp.route("/aliases")
def aliases_page():
    return _serve("aliases.html")


@pages_bp.route("/quality-domains")
def quality_domains_page():
    return _serve("quality-domains.html")
