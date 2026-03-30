"""
WAF Classifier — Page-serving routes.
Simple routes that serve static HTML files.
"""

from flask import Blueprint, send_from_directory, redirect

pages_bp = Blueprint("pages_bp", __name__)


@pages_bp.route("/")
def home():
    return send_from_directory("static", "home.html")


@pages_bp.route("/classify")
def classify_page():
    return send_from_directory("static", "index.html")


@pages_bp.route("/dashboard")
def dashboard():
    return redirect("/history")


@pages_bp.route("/history")
def history():
    return send_from_directory("static", "history.html")


@pages_bp.route("/waf-reference")
def waf_reference():
    return send_from_directory("static", "waf-reference.html")


@pages_bp.route("/lineage")
def lineage_page():
    return send_from_directory("static", "lineage.html")


@pages_bp.route("/settings")
def settings_page():
    """Serve the admin settings page."""
    return send_from_directory("static", "settings.html")


@pages_bp.route("/teams")
def teams_page():
    return send_from_directory("static", "teams.html")


@pages_bp.route("/merge")
def merge_page():
    return send_from_directory("static", "merge.html")
