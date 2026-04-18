from flask import Blueprint, render_template


ui_bp = Blueprint("ui", __name__)


@ui_bp.get("/")
def index_page():
    return render_template("index.html")


@ui_bp.get("/analyze")
def analyze_page():
    return render_template("analyze.html")


@ui_bp.get("/acl-optimize")
def acl_optimize_page():
    return render_template("acl_optimize.html")
