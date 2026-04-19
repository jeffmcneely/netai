import logging

from flask import Flask, jsonify
from dotenv import load_dotenv

from app.config import Config
from app.routes.api import api_bp
from app.routes.ui import ui_bp
from app.services.s3_manager import S3Manager


load_dotenv()


def _validate_required_config(app: Flask) -> None:
    missing = []
    if not app.config.get("S3_BUCKET"):
        missing.append("S3_BUCKET")
    if not app.config.get("BATFISH_SERVER"):
        missing.append("BATFISH_SERVER")

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variable(s): {names}")


def _bootstrap_aws_role_if_configured(app: Flask) -> None:
    aws_role = app.config.get("AWS_ROLE", "")
    if not aws_role:
        return

    s3 = S3Manager(
        bucket=app.config["S3_BUCKET"],
        region=app.config["AWS_REGION"],
        aws_role=aws_role,
        role_session_name=app.config.get("AWS_ROLE_SESSION_NAME", "netai-session"),
    )
    s3.bootstrap_assumed_role()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    logging.getLogger("app.services.batfish_manager").setLevel(logging.DEBUG)
    logging.getLogger("app.services.claude_manager").setLevel(logging.DEBUG)
    logging.getLogger("app.services.openai_manager").setLevel(logging.DEBUG)

    _validate_required_config(app)
    _bootstrap_aws_role_if_configured(app)

    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
