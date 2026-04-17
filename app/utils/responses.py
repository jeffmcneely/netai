from datetime import datetime, timezone

from flask import jsonify


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok(data=None, status=200):
    payload = {
        "status": "success",
        "timestamp": _now_iso(),
        "data": data if data is not None else {},
    }
    return jsonify(payload), status


def fail(message: str, code: str, status=400, field=None):
    payload = {
        "status": "error",
        "timestamp": _now_iso(),
        "error": {
            "code": code,
            "message": message,
        },
    }
    if field:
        payload["error"]["field"] = field
    return jsonify(payload), status
