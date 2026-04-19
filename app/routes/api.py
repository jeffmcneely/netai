from flask import Blueprint, current_app, request
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from typing import Optional
from uuid import uuid4

from app.services.batfish_manager import BatfishManager, build_header_constraints
from app.services.claude_manager import ClaudeManager, ClaudeTimeoutError
from app.services.ip_finder import find_object_matches, find_string_matches, normalize_max_results
from app.services.openai_manager import OpenAIManager, OpenAITimeoutError
from app.services.s3_manager import S3Manager
from app.utils.responses import fail, ok
from app.utils.validators import (
    ValidationError,
    parse_acl_generate_commands_payload,
    parse_acl_optimize_payload,
    parse_acl_remove_junk_payload,
    parse_acl_verify_payload,
    parse_csv,
    parse_int_values,
    parse_ip_values,
    parse_ports,
    sanitize_filename,
    validate_folder_name,
)


api_bp = Blueprint("api", __name__)
_ACL_REMOVE_JUNK_JOBS: dict[str, dict] = {}
_ACL_REMOVE_JUNK_LOCK = Lock()
_ACL_REMOVE_JUNK_TTL_SECONDS = 900


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _cleanup_remove_junk_jobs() -> None:
    cutoff = _utc_now() - timedelta(seconds=_ACL_REMOVE_JUNK_TTL_SECONDS)
    with _ACL_REMOVE_JUNK_LOCK:
        stale_ids = []
        for job_id, job in _ACL_REMOVE_JUNK_JOBS.items():
            if job.get("state") not in {"completed", "failed"}:
                continue
            updated_at = job.get("updated_at")
            try:
                updated_dt = datetime.fromisoformat(str(updated_at))
            except Exception:
                stale_ids.append(job_id)
                continue
            if updated_dt < cutoff:
                stale_ids.append(job_id)

        for job_id in stale_ids:
            _ACL_REMOVE_JUNK_JOBS.pop(job_id, None)


def _get_remove_junk_job(job_id: str) -> Optional[dict]:
    with _ACL_REMOVE_JUNK_LOCK:
        job = _ACL_REMOVE_JUNK_JOBS.get(job_id)
        if not job:
            return None
        return dict(job)


def _run_remove_junk_job(
    job_id: str,
    platform: str,
    current_acl: str,
    start_line: int,
    batfish_server: str,
) -> None:
    def _publish_progress(update: dict) -> None:
        with _ACL_REMOVE_JUNK_LOCK:
            job = _ACL_REMOVE_JUNK_JOBS.get(job_id)
            if not job:
                return
            progress = dict(job.get("progress") or {})
            progress.update(update)
            job["progress"] = progress
            job["updated_at"] = _iso_now()

    try:
        with _ACL_REMOVE_JUNK_LOCK:
            job = _ACL_REMOVE_JUNK_JOBS.get(job_id)
            if not job:
                return
            job["state"] = "running"
            job["updated_at"] = _iso_now()

        bf = BatfishManager(server=batfish_server)
        result = bf.reduce_acl_remove_junk(
            platform=platform,
            current_acl=current_acl,
            start_line=start_line,
            progress_cb=_publish_progress,
        )

        with _ACL_REMOVE_JUNK_LOCK:
            job = _ACL_REMOVE_JUNK_JOBS.get(job_id)
            if not job:
                return
            job["state"] = "completed"
            job["result"] = result
            job["updated_at"] = _iso_now()
            job["progress"] = {
                **(job.get("progress") or {}),
                "message": "completed",
            }
    except Exception as exc:
        with _ACL_REMOVE_JUNK_LOCK:
            job = _ACL_REMOVE_JUNK_JOBS.get(job_id)
            if not job:
                return
            job["state"] = "failed"
            job["error"] = str(exc)
            job["updated_at"] = _iso_now()


def _s3_manager() -> S3Manager:
    return S3Manager(
        bucket=current_app.config.get("S3_BUCKET", ""),
        region=current_app.config.get("AWS_REGION", "us-east-1"),
        aws_role=current_app.config.get("AWS_ROLE", ""),
        role_session_name=current_app.config.get("AWS_ROLE_SESSION_NAME", "netai-session"),
    )


def _batfish_manager() -> BatfishManager:
    return BatfishManager(server=current_app.config.get("BATFISH_SERVER", ""))


def _openai_manager(model_override: Optional[str] = None) -> OpenAIManager:
    model = model_override or current_app.config.get("OPENAI_MODEL", "gpt-5.4")
    return OpenAIManager(
        api_key=current_app.config.get("OPENAI_API_KEY", ""),
        model=model,
    )


def _claude_manager(model_override: Optional[str] = None) -> ClaudeManager:
    model = model_override or current_app.config.get("CLAUDE_MODEL", "claude-sonnet-4-5")
    return ClaudeManager(
        api_key=current_app.config.get("CLAUDE_API_KEY", ""),
        model=model,
    )


def _acl_llm_manager(model_override: Optional[str] = None):
    model = (model_override or current_app.config.get("OPENAI_MODEL", "gpt-5.4")).strip()
    if model.startswith("claude"):
        return _claude_manager(model)
    return _openai_manager(model)


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


def _normalize_node_name(value: object) -> str:
    if isinstance(value, dict):
        for key in ("hostname", "name", "node"):
            nested = value.get(key)
            if nested:
                return str(nested).strip()
        return ""
    return str(value or "").strip()


def _extract_row_node_name(row: dict) -> str:
    for key in ("Node", "Hostname", "Name"):
        if key in row:
            parsed = _normalize_node_name(row.get(key))
            if parsed:
                return parsed
    return ""


def _canonicalize_for_compare(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        canonical_items = [_canonicalize_for_compare(item) for item in value]
        return sorted(canonical_items, key=lambda item: json.dumps(item, sort_keys=True, default=str))

    if isinstance(value, dict):
        return {
            str(key): _canonicalize_for_compare(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }

    return str(value)


def _build_snmp_community_report(node_rows: list[dict], structure_rows: list[dict]) -> dict:
    all_nodes = sorted({node for node in (_extract_row_node_name(row) for row in node_rows) if node})
    per_node_values: dict[str, dict[str, object]] = {node: {} for node in all_nodes}

    for row in structure_rows:
        node_name = _extract_row_node_name(row)
        if not node_name:
            continue

        structure_name = str(row.get("Structure_Name") or row.get("StructureName") or "").strip()
        if not structure_name:
            continue

        struct_type = str(row.get("Structure_Type") or row.get("StructureType") or "").strip()
        if "community_match_expr" not in struct_type.casefold():
            continue

        definition = row.get("Structure_Definition", row.get("StructureDefinition"))
        canonical_definition = _canonicalize_for_compare(definition)
        per_node_values.setdefault(node_name, {})[structure_name] = canonical_definition

    signatures: dict[str, str] = {}
    signature_counts = Counter()
    for node_name, definitions in per_node_values.items():
        signature_payload = sorted(
            (
                {
                    "name": name,
                    "definition": definition,
                }
                for name, definition in definitions.items()
            ),
            key=lambda item: item["name"],
        )
        signature = json.dumps(signature_payload, sort_keys=True, separators=(",", ":"), default=str)
        signatures[node_name] = signature
        signature_counts[signature] += 1

    baseline_signature = "[]"
    baseline_count = 0
    if signature_counts:
        baseline_count = max(signature_counts.values())
        candidate_signatures = sorted(
            signature
            for signature, count in signature_counts.items()
            if count == baseline_count
        )
        baseline_signature = candidate_signatures[0]

    baseline_entries = json.loads(baseline_signature)
    baseline_map = {str(item.get("name", "")): item.get("definition") for item in baseline_entries}

    master_map: dict[str, object] = {}
    for node_map in per_node_values.values():
        for name, definition in node_map.items():
            master_map.setdefault(name, definition)

    master_values = [
        {
            "name": name,
            "definition": definition,
        }
        for name, definition in sorted(master_map.items(), key=lambda item: item[0])
    ]

    mismatch_rows: list[dict] = []
    for node_name in sorted(per_node_values):
        current_map = per_node_values[node_name]
        missing = sorted(name for name in baseline_map if name not in current_map)
        extra = sorted(name for name in current_map if name not in baseline_map)

        different = []
        for name in sorted(name for name in current_map if name in baseline_map):
            if current_map[name] != baseline_map[name]:
                different.append(
                    {
                        "name": name,
                        "expected_definition": baseline_map[name],
                        "actual_definition": current_map[name],
                    }
                )

        if not missing and not extra and not different:
            continue

        mismatch_rows.append(
            {
                "node": node_name,
                "missing": missing,
                "extra": extra,
                "different": different,
                "baseline_entry_count": len(baseline_map),
                "node_entry_count": len(current_map),
            }
        )

    return {
        "master_values": master_values,
        "mismatch_rows": mismatch_rows,
        "rows": mismatch_rows,
        "baseline_signature_meta": {
            "node_count": len(per_node_values),
            "majority_count": baseline_count,
            "baseline_entry_count": len(baseline_map),
        },
    }


def _parse_find_object_payload(payload: dict) -> tuple[str, str, int, str]:
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

    raw_find_mode = str(payload.get("find_mode", "contains")).strip().lower()
    if not raw_find_mode:
        raw_find_mode = "contains"
    if raw_find_mode not in {"contains", "exact"}:
        raise ValidationError("find_mode must be either 'contains' or 'exact'")

    return config_folder, parsed_values[0], max_results, raw_find_mode


def _parse_find_string_payload(payload: dict) -> tuple[str, str, int]:
    if payload is None:
        raise ValidationError("JSON payload is required")

    config_folder = _resolve_config_folder(payload)
    find_text = str(payload.get("find_text", "")).strip()
    if not find_text:
        raise ValidationError("find_text is required")

    try:
        max_results = normalize_max_results(payload.get("max_results"))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    return config_folder, find_text, max_results


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


@api_bp.post("/acl/optimize")
def acl_optimize():
    try:
        payload = request.get_json(force=True)
        platform, current_acl, model = parse_acl_optimize_payload(payload)

        optimized_acl = _acl_llm_manager(model).optimize_acl(current_acl)
        return ok(
            {
                "platform": platform,
                "model": model or current_app.config.get("OPENAI_MODEL", "gpt-5.4"),
                "candidate": optimized_acl,
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except (OpenAITimeoutError, ClaudeTimeoutError) as exc:
        return fail(str(exc), "LLM_TIMEOUT", status=504)
    except Exception as exc:
        return fail(str(exc), "ACL_OPTIMIZE_ERROR", status=500)


@api_bp.post("/acl/verify")
def acl_verify():
    try:
        payload = request.get_json(force=True)
        platform, original_acl, compressed_acl = parse_acl_verify_payload(payload)

        bf = _batfish_manager()
        original_snapshot = bf.init_snapshot_from_text(
            original_acl,
            platform=platform,
            snapshot_name="original",
        )
        compressed_snapshot = bf.init_snapshot_from_text(
            compressed_acl,
            platform=platform,
            snapshot_name="compressed",
        )
        rows = bf.run_compare_filters(
            snapshot_name=compressed_snapshot,
            reference_snapshot=original_snapshot,
        )

        return ok(
            {
                "platform": platform,
                "original_snapshot": original_snapshot,
                "compressed_snapshot": compressed_snapshot,
                "rows": rows,
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "ACL_VERIFY_ERROR", status=500)


@api_bp.post("/acl/generate-commands")
def acl_generate_commands():
    try:
        payload = request.get_json(force=True)
        mapped_platform, current_acl, candidate_acl, model = parse_acl_generate_commands_payload(payload)

        commands = _acl_llm_manager(model).generate_acl_commands(
            platform_context=mapped_platform,
            current_acl=current_acl,
            candidate_acl=candidate_acl,
        )
        return ok({"commands": commands, "model": model or current_app.config.get("OPENAI_MODEL", "gpt-5.4")})
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except (OpenAITimeoutError, ClaudeTimeoutError) as exc:
        return fail(str(exc), "LLM_TIMEOUT", status=504)
    except Exception as exc:
        return fail(str(exc), "ACL_GENERATE_COMMANDS_ERROR", status=500)


@api_bp.post("/acl/remove-junk/start")
def acl_remove_junk_start():
    try:
        _cleanup_remove_junk_jobs()
        payload = request.get_json(force=True)
        platform, current_acl, start_line = parse_acl_remove_junk_payload(payload)

        job_id = uuid4().hex
        new_job = {
            "job_id": job_id,
            "state": "queued",
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
            "error": None,
            "progress": {
                "iteration": 0,
                "total_iterations": max(len(current_acl.splitlines()) - max(start_line - 1, 0), 0),
                "line_number": None,
                "lines_removed": 0,
                "last_decision": "queued",
                "last_compare_rows": None,
                "message": "queued",
            },
            "result": None,
        }

        with _ACL_REMOVE_JUNK_LOCK:
            _ACL_REMOVE_JUNK_JOBS[job_id] = new_job

        batfish_server = current_app.config.get("BATFISH_SERVER", "")
        worker = Thread(
            target=_run_remove_junk_job,
            args=(job_id, platform, current_acl, start_line, batfish_server),
            daemon=True,
        )
        worker.start()

        return ok({"job_id": job_id, "state": "queued"}, status=202)
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "ACL_REMOVE_JUNK_START_ERROR", status=500)


@api_bp.get("/acl/remove-junk/status/<job_id>")
def acl_remove_junk_status(job_id: str):
    try:
        _cleanup_remove_junk_jobs()
        job = _get_remove_junk_job(job_id)
        if not job:
            return fail("job not found", "JOB_NOT_FOUND", status=404)

        return ok(
            {
                "job_id": job_id,
                "state": job.get("state"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "progress": job.get("progress") or {},
                "error": job.get("error"),
            }
        )
    except Exception as exc:
        return fail(str(exc), "ACL_REMOVE_JUNK_STATUS_ERROR", status=500)


@api_bp.get("/acl/remove-junk/result/<job_id>")
def acl_remove_junk_result(job_id: str):
    try:
        _cleanup_remove_junk_jobs()
        job = _get_remove_junk_job(job_id)
        if not job:
            return fail("job not found", "JOB_NOT_FOUND", status=404)

        state = job.get("state")
        if state == "failed":
            return fail(job.get("error") or "job failed", "JOB_FAILED", status=500)
        if state != "completed":
            return fail("job is not completed", "JOB_NOT_COMPLETED", status=409)

        result = job.get("result") or {}
        return ok(
            {
                "job_id": job_id,
                "state": state,
                "final_candidate": result.get("final_candidate", ""),
                "removed_lines": result.get("removed_lines") or [],
                "iterations": result.get("iterations") or [],
                "summary": result.get("summary") or {},
            }
        )
    except Exception as exc:
        return fail(str(exc), "ACL_REMOVE_JUNK_RESULT_ERROR", status=500)


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


@api_bp.post("/unreachable-rules")
def unreachable_rules():
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
        return fail(str(exc), "UNREACHABLE_RULES_ERROR", status=500)


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


@api_bp.post("/snmp-check")
def snmp_check():
    try:
        payload = request.get_json(force=True)
        config_folder = _resolve_config_folder(payload)

        s3 = _s3_manager()
        bf = _batfish_manager()
        snapshot_name = bf.init_snapshot(s3.get_snapshot_zip_data(config_folder), config_folder)

        node_rows = bf.run_node_properties()
        structure_rows = bf.run_named_structures()
        report = _build_snmp_community_report(node_rows=node_rows, structure_rows=structure_rows)

        return ok(
            {
                "snapshot_name": snapshot_name,
                **report,
            }
        )
    except ValidationError as exc:
        return fail(str(exc), "VALIDATION_ERROR", status=400)
    except Exception as exc:
        return fail(str(exc), "SNMP_CHECK_ERROR", status=500)


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
        config_folder, search_ip, max_results, find_mode = _parse_find_object_payload(payload)

        s3 = _s3_manager()
        files = s3.list_config_files(config_folder)
        files_with_lines = ((filename, s3.iter_config_file_lines(config_folder, filename)) for filename in files)

        normalized_input, matches, truncated = find_object_matches(
            search_input=search_ip,
            files_with_lines=files_with_lines,
            max_results=max_results,
            find_mode=find_mode,
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


@api_bp.post("/find-string")
def find_string():
    try:
        payload = request.get_json(force=True)
        config_folder, find_text, max_results = _parse_find_string_payload(payload)

        s3 = _s3_manager()
        files = s3.list_config_files(config_folder)
        files_with_lines = ((filename, s3.iter_config_file_lines(config_folder, filename)) for filename in files)

        normalized_input, matches, truncated = find_string_matches(
            search_text=find_text,
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
        return fail(str(exc), "FIND_STRING_ERROR", status=500)


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
