from flask import Blueprint, current_app, request

from app.services.batfish_manager import BatfishManager, build_header_constraints
from app.services.ip_finder import find_object_matches, normalize_max_results
from app.services.s3_manager import S3Manager
from app.utils.responses import fail, ok
from app.utils.validators import (
    ValidationError,
    parse_csv,
    parse_int_values,
    parse_ip_values,
    parse_ports,
    sanitize_filename,
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


def _normalize_acl_filter_name(raw_value: object) -> str:
    filter_name = str(raw_value or "").strip()
    if not filter_name:
        raise ValidationError("filter_name is required")

    if filter_name.isdigit():
        return f"/^{filter_name}/"

    return filter_name


def _parse_find_object_payload(payload: dict) -> tuple[str, str, int]:
    if payload is None:
        raise ValidationError("JSON payload is required")

    config_folder = _resolve_config_folder(payload)

    search_ip = str(payload.get("ip", "")).strip()
    parsed_values = parse_ip_values(search_ip, "ip")
    if len(parsed_values) != 1:
        raise ValidationError("Provide exactly one IP/CIDR value for ip")

    try:
        max_results = normalize_max_results(payload.get("max_results"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    return config_folder, parsed_values[0], max_results


def _parse_find_object_file_query() -> tuple[str, str, int]:
    config_folder = validate_folder_name(str(request.args.get("config_folder", "")).strip())
    filename = str(request.args.get("filename", "")).strip()
    if not filename:
        raise ValidationError("filename is required")

    safe_filename = sanitize_filename(filename)

    raw_jump_line = str(request.args.get("jump_line", "")).strip()
    if not raw_jump_line:
        return config_folder, safe_filename, 0

    if not raw_jump_line.isdigit() or int(raw_jump_line) < 1:
        raise ValidationError("jump_line must be a positive integer")

    return config_folder, safe_filename, int(raw_jump_line)


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


@api_bp.post("/interfaces")
def interfaces():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)
        node_hostname = str(payload.get("node_hostname", "")).strip()

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)
        rows = bf.run_interface_properties(node_hostname=node_hostname or None)

        return ok({"snapshot_name": snapshot_name, "rows": rows})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "INTERFACES_ERROR", status=500)


@api_bp.post("/explorer")
def explorer():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)
        rows = bf.run_node_properties()

        return ok({"snapshot_name": snapshot_name, "rows": rows})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "EXPLORER_ERROR", status=500)


@api_bp.post("/vlans")
def vlans():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)
        node_hostname = str(payload.get("node_hostname", "")).strip()

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)
        rows = bf.run_switched_vlan_properties(node_hostname=node_hostname or None)

        return ok({"snapshot_name": snapshot_name, "rows": rows})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "VLANS_ERROR", status=500)


@api_bp.post("/node-acl-search")
def node_acl_search():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)
        node_hostname = str(payload.get("node_hostname", "")).strip()
        filter_name = _normalize_acl_filter_name(payload.get("filter_name"))

        if not node_hostname:
            raise ValidationError("node_hostname is required")

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)
        rows = bf.run_search_filters_for_acl(node_hostname=node_hostname, filter_name=filter_name)

        return ok(
            {
                "snapshot_name": snapshot_name,
                "node_hostname": node_hostname,
                "filter_name": filter_name,
                "rows": rows,
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "NODE_ACL_SEARCH_ERROR", status=500)


@api_bp.post("/find-object")
def find_object():
    try:
        payload = request.get_json(force=True)
        config_folder, search_ip, max_results = _parse_find_object_payload(payload)

        s3 = _s3_manager()
        files = s3.list_config_files(config_folder)
        files_with_lines = ((filename, s3.iter_config_file_lines(config_folder, filename)) for filename in files)

        normalized_input, matches, truncated = find_object_matches(
            search_input=search_ip,
            files_with_lines=files_with_lines,
            max_results=max_results,
        )

        return ok(
            {
                "config_folder": config_folder,
                "input": normalized_input,
                "total_matches": len(matches),
                "truncated": truncated,
                "max_results": max_results,
                "results": matches,
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "FIND_OBJECT_ERROR", status=500)


@api_bp.get("/find-object/file")
def find_object_file():
    try:
        config_folder, filename, jump_line = _parse_find_object_file_query()

        s3 = _s3_manager()
        text = s3.get_config_file_text(config_folder, filename)
        lines = text.split("\n") if text else []

        if jump_line > len(lines):
            jump_line = 0

        return ok(
            {
                "config_folder": config_folder,
                "filename": filename,
                "jump_line": jump_line,
                "total_lines": len(lines),
                "lines": [
                    {
                        "line_number": index + 1,
                        "content": line,
                        "is_jump_target": jump_line > 0 and jump_line == (index + 1),
                    }
                    for index, line in enumerate(lines)
                ],
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except FileNotFoundError as exc:
        return fail(str(exc), "FILE_NOT_FOUND", status=404)
    except Exception as exc:
        return fail(str(exc), "FIND_OBJECT_FILE_ERROR", status=500)
