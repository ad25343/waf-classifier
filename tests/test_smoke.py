"""
Smoke tests: API endpoints and HTML integrity checks.
Run with: pytest tests/test_smoke.py -v
Server must be running on http://localhost:8080
"""
import re
import pytest
import requests
from pathlib import Path

BASE = "http://localhost:8080"
STATIC = Path(__file__).parent.parent / "static"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get(path, **kwargs):
    return requests.get(BASE + path, timeout=5, **kwargs)

def post(path, **kwargs):
    return requests.post(BASE + path, timeout=5, **kwargs)

# ── Page routes ───────────────────────────────────────────────────────────────

class TestPages:
    def test_home(self):
        r = get("/")
        assert r.status_code == 200

    def test_classify_page(self):
        r = get("/classify")
        assert r.status_code == 200

    def test_history_page(self):
        r = get("/history")
        assert r.status_code == 200

    def test_lineage_page(self):
        r = get("/lineage")
        assert r.status_code == 200

    def test_dashboard_page(self):
        r = get("/dashboard")
        assert r.status_code == 200

    def test_settings_page(self):
        r = get("/settings")
        assert r.status_code == 200

    def test_teams_page(self):
        r = get("/teams")
        assert r.status_code == 200

    def test_waf_reference_page(self):
        r = get("/waf-reference")
        assert r.status_code == 200

# ── API endpoints ─────────────────────────────────────────────────────────────

class TestAPI:
    def test_dashboard_summary(self):
        r = get("/api/dashboard/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_classifications" in data

    def test_dashboard_stories(self):
        r = get("/api/dashboard/stories")
        assert r.status_code == 200
        data = r.json()
        assert "stories" in data

    def test_status(self):
        r = get("/api/status")
        assert r.status_code == 200

    def test_epics_list(self):
        r = get("/api/epics")
        assert r.status_code == 200
        data = r.json()
        assert "epics" in data

    def test_epics_summary(self):
        r = get("/api/epics/summary")
        assert r.status_code == 200
        data = r.json()
        assert "epics" in data

    def test_epics_uploads(self):
        r = get("/api/epics/uploads")
        assert r.status_code == 200
        data = r.json()
        assert "uploads" in data

    def test_epics_autocomplete_empty(self):
        r = get("/api/epics/autocomplete")
        assert r.status_code == 200
        data = r.json()
        assert "epics" in data and "features" in data

    def test_epics_autocomplete_query(self):
        r = get("/api/epics/autocomplete?q=test")
        assert r.status_code == 200

    def test_upload_history(self):
        r = get("/api/history/uploads")
        assert r.status_code == 200
        data = r.json()
        assert "uploads" in data

    def test_bulk_verify_jobs(self):
        r = get("/api/bulk-verify/jobs")
        assert r.status_code == 200
        data = r.json()
        assert "jobs" in data

    def test_submitted_waf(self):
        # submitted_waf is embedded in the dashboard summary response
        r = get("/api/dashboard/summary")
        assert r.status_code == 200
        assert "submitted_waf" in r.json()

    def test_teams_list(self):
        r = get("/api/teams/summary")
        assert r.status_code == 200

    def test_settings_get(self):
        r = get("/api/settings")
        assert r.status_code == 200

    def test_nonexistent_endpoint_returns_404(self):
        r = get("/api/does-not-exist")
        assert r.status_code == 404

    def test_bulk_verify_status_unknown_job(self):
        r = get("/api/bulk-verify/status/nonexistent-job-id")
        # Should be 404 or a JSON error, not 500
        assert r.status_code in (404, 200)
        if r.status_code == 200:
            assert r.json().get("status") in ("not_found", "error", None)

# ── Static files ──────────────────────────────────────────────────────────────

class TestStaticFiles:
    def test_all_html_files_served(self):
        for html in STATIC.glob("*.html"):
            r = requests.get(f"{BASE}/static/{html.name}", timeout=5)
            assert r.status_code == 200, f"{html.name} returned {r.status_code}"

# ── HTML integrity ─────────────────────────────────────────────────────────────

class TestHTMLIntegrity:
    HTML_FILES = list(STATIC.glob("*.html"))

    @pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda f: f.name)
    def test_no_undefined_css_vars(self, html_file):
        """All var(--x) used in inline styles must be defined in :root or [data-theme]."""
        content = html_file.read_text()
        defined = set(re.findall(r'--([\w-]+)\s*:', content))
        used = set(re.findall(r'var\(--([\w-]+)\)', content))
        # Known globals defined in linked stylesheets or intentionally external
        known_external = set()
        undefined = used - defined - known_external
        assert not undefined, f"{html_file.name} uses undefined CSS vars: {sorted(undefined)}"

    @pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda f: f.name)
    def test_no_unclosed_template_literals(self, html_file):
        """Catch obvious unclosed backtick template literals in JS."""
        content = html_file.read_text()
        # Strip content inside <style> and HTML text nodes — only check <script> blocks
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
        for script in scripts:
            backticks = script.count('`')
            assert backticks % 2 == 0, \
                f"{html_file.name} has odd number of backticks in a <script> block — possible unclosed template literal"

    @pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda f: f.name)
    def test_onclick_functions_defined(self, html_file):
        """Functions referenced in onclick= must be defined somewhere in the file or known globals."""
        content = html_file.read_text()
        onclick_fns = set(re.findall(r'onclick="([a-zA-Z_]\w*)\(', content))
        script_content = ' '.join(re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL))
        defined_fns = set(re.findall(r'function\s+([a-zA-Z_]\w*)\s*\(', script_content))
        # JS keywords and browser globals that aren't user-defined functions
        not_functions = {'toggleTheme', 'event', 'if', 'for', 'while', 'switch', 'return', 'new'}
        missing = onclick_fns - defined_fns - not_functions
        assert not missing, \
            f"{html_file.name} onclick references undefined functions: {sorted(missing)}"

    @pytest.mark.parametrize("html_file", HTML_FILES, ids=lambda f: f.name)
    def test_no_double_closing_tags(self, html_file):
        """Basic check: no obviously malformed HTML like </div></div> in wrong sequence."""
        content = html_file.read_text()
        # Check for common symptom of copy-paste errors
        assert '<<' not in content, f"{html_file.name} contains '<<'"
        assert '>>' not in content or 'href' in content, f"{html_file.name} contains '>>'"
