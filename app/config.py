import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key")
    S3_BUCKET = os.environ.get("S3_BUCKET", "").strip()
    BATFISH_SERVER = os.environ.get("BATFISH_SERVER", "").strip()
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_ROLE = os.environ.get("AWS_ROLE", "").strip()
    AWS_ROLE_SESSION_NAME = os.environ.get("AWS_ROLE_SESSION_NAME", "netai-session").strip() or "netai-session"
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(100 * 1024 * 1024)))
