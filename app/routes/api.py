from flask import Blueprint, current_app, request

from app.services.batfish_manager import BatfishManager, build_header_constraints
from app.services.s3_manager import S3Manager
from app.utils.responses import fail, ok
from app.utils.validators import (
    ValidationError,
    parse_csv,
    parse_int_values,
    parse_ip_values,
    parse_ports,
    validate_folder_name,
)


api_bp = Blueprint("api", __name__)


def _s3_manager() -> S3Manager:
    return S3Manager(
        bucket=current_app.config.get("S3_BUCKET", ""),
        region=current_app.config.get("AWS_REGION", "us-east-1"),
        aws_role=current_app.config.get("AWS_ROLE", ""),
        role_session_name=current_app.config.get("AWS_ROLE_SESSION_NAME", "netai-session"),
    )


def _batfish_manager() -> BatfishManager:
    return BatfishManager(server=current_app.config.get("BATFISH_SERVER", ""))


def _is_truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_config_folder(payload: dict) -> str:
    use_new = _is_truthy(payload.get("use_new"))
    folder = (payload.get("new_folder_name") if use_new else payload.get("config_folder")) or ""
    return validate_folder_name(folder.strip())


def _normalize_search_filters(raw: dict) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("search_filters must be an object")

    normalized = {
        "srcIps": parse_ip_values(",".join(raw.get("srcIps", [])) if isinstance(raw.get("srcIps"), list) else str(raw.get("srcIps", "")), "srcIps"),
        "dstIps": parse_ip_values(",".join(raw.get("dstIps", [])) if isinstance(raw.get("dstIps"), list) else str(raw.get("dstIps", "")), "dstIps"),
        "srcPorts": parse_ports(",".join(raw.get("srcPorts", [])) if isinstance(raw.get("srcPorts"), list) else str(raw.get("srcPorts", "")),),
        "dstPorts": parse_ports(",".join(raw.get("dstPorts", [])) if isinstance(raw.get("dstPorts"), list) else str(raw.get("dstPorts", "")),),
        "applications": parse_csv(",".join(raw.get("applications", [])) if isinstance(raw.get("applications"), list) else str(raw.get("applications", "")),),
        "ipProtocols": parse_csv(",".join(raw.get("ipProtocols", [])) if isinstance(raw.get("ipProtocols"), list) else str(raw.get("ipProtocols", "")),),
        "icmpCodes": parse_int_values(",".join(raw.get("icmpCodes", [])) if isinstance(raw.get("icmpCodes"), list) else str(raw.get("icmpCodes", "")), "icmpCodes"),
        "icmpTypes": parse_int_values(",".join(raw.get("icmpTypes", [])) if isinstance(raw.get("icmpTypes"), list) else str(raw.get("icmpTypes", "")), "icmpTypes"),
        "dscps": parse_int_values(",".join(raw.get("dscps", [])) if isinstance(raw.get("dscps"), list) else str(raw.get("dscps", "")), "dscps"),
        "ecns": parse_int_values(",".join(raw.get("ecns", [])) if isinstance(raw.get("ecns"), list) else str(raw.get("ecns", "")), "ecns"),
        "packetLengths": parse_int_values(",".join(raw.get("packetLengths", [])) if isinstance(raw.get("packetLengths"), list) else str(raw.get("packetLengths", "")), "packetLengths"),
        "fragmentOffsets": parse_int_values(",".join(raw.get("fragmentOffsets", [])) if isinstance(raw.get("fragmentOffsets"), list) else str(raw.get("fragmentOffsets", "")), "fragmentOffsets"),
        "tcpFlags": [flag.lower() for flag in (raw.get("tcpFlags", []) if isinstance(raw.get("tcpFlags"), list) else parse_csv(str(raw.get("tcpFlags", ""))))],
    }

    valid_flags = {"ack", "est", "rst", "syn", "synack"}
    for flag in normalized["tcpFlags"]:
        if flag not in valid_flags:
            raise ValidationError(f"Invalid tcp flag '{flag}'")

    return normalized


@api_bp.get("/configs")
def list_configs():
    try:
        folders = _s3_manager().list_config_folders()
        return ok({"folders": folders})
    except Exception as exc:
        return fail(str(exc), "S3_LIST_ERROR", status=500)


@api_bp.post("/upload")
def upload_files():
    try:
        payload = request.form.to_dict()
        config_folder = _resolve_config_folder(payload)

        files = request.files.getlist("files")
        if not files:
            return fail("No files provided", "NO_FILES", status=400)

        manager = _s3_manager()
        if _is_truthy(payload.get("use_new")):
            manager.ensure_folder(config_folder)

        uploaded = [manager.upload_file(config_folder, f) for f in files]
        return ok({"folder": config_folder, "uploaded": uploaded}, status=201)
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "UPLOAD_ERROR", status=500)


@api_bp.post("/analyze")
def analyze():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)
        rows = bf.run_filter_line_reachability()

        return ok({"snapshot_name": snapshot_name, "rows": rows})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "ANALYZE_ERROR", status=500)


@api_bp.post("/search")
def search():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)
        filters = _normalize_search_filters(payload.get("search_filters", {}))

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)

        headers = build_header_constraints(filters)
        rows = bf.run_search_filters(headers)

        return ok({"snapshot_name": snapshot_name, "rows": rows, "applied_filters": filters})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "SEARCH_ERROR", status=500)
