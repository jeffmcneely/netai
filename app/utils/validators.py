import ipaddress
import re
from typing import List


FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ACL_PLATFORMS = {
    "arista",
    "bigip",
    "ciscoasa",
    "cisco-nx",
    "cisco-xr",
    "force10",
    "foundry",
    "juniper",
    "mrv",
    "paloalto",
}
ACL_PLATFORM_PROMPT_MAP = {
    "arista": "arista",
    "bigip": "f5 bigip",
    "cisco-nx": "cisco NX-OS",
    "cisco-xr": "cisco IOS-XR",
    "force10": "force10",
    "foundry": "foundry",
    "juniper": "juniper junos",
    "mrv": "mrv",
    "paloalto": "palo alto",
    "ciscoasa": "cisco asa",
}
OPENAI_MODELS = {
    "gpt-5.2",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.2-mini",
}


class ValidationError(ValueError):
    pass


def validate_folder_name(name: str) -> str:
    if not name:
        raise ValidationError("Folder name is required")
    if "/" in name or ".." in name or "~" in name:
        raise ValidationError("Folder name contains forbidden characters")
    if not FOLDER_RE.match(name):
        raise ValidationError("Folder name must be 1-64 chars of letters, numbers, _ or -")
    return name


def parse_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_ports(value: str) -> List[str]:
    values = parse_csv(value)
    parsed: List[str] = []
    for token in values:
        if "-" in token:
            parts = token.split("-", 1)
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValidationError(f"Invalid port range '{token}'")
            start = int(parts[0])
            end = int(parts[1])
            if start < 1 or end > 65535 or start > end:
                raise ValidationError(f"Invalid port range '{token}'")
            parsed.append(f"{start}-{end}")
        else:
            if not token.isdigit():
                raise ValidationError(f"Invalid port '{token}'")
            port = int(token)
            if port < 1 or port > 65535:
                raise ValidationError(f"Port '{token}' is out of range")
            parsed.append(str(port))
    return parsed


def parse_int_values(value: str, field_name: str) -> List[int]:
    values = parse_csv(value)
    parsed: List[int] = []
    for token in values:
        if not token.isdigit():
            raise ValidationError(f"Invalid value '{token}' for {field_name}")
        parsed.append(int(token))
    return parsed


def parse_ip_values(value: str, field_name: str) -> List[str]:
    values = parse_csv(value)
    parsed: List[str] = []
    for token in values:
        try:
            if "/" in token:
                ipaddress.ip_network(token, strict=False)
            else:
                ipaddress.ip_address(token)
        except ValueError as exc:
            raise ValidationError(f"Invalid IP/CIDR '{token}' for {field_name}") from exc
        parsed.append(token)
    return parsed


def sanitize_filename(filename: str) -> str:
    if not filename:
        raise ValidationError("Filename is empty")
    clean = filename.replace("\\", "/").split("/")[-1]
    if clean in {"", ".", ".."}:
        raise ValidationError("Invalid filename")
    if len(clean) > 255:
        raise ValidationError("Filename is too long")
    return clean


def validate_acl_platform(raw_value: object) -> str:
    platform = str(raw_value or "").strip().lower()
    if not platform:
        raise ValidationError("platform is required")
    if platform not in ACL_PLATFORMS:
        allowed = ", ".join(sorted(ACL_PLATFORMS))
        raise ValidationError(f"platform must be one of: {allowed}")
    return platform


def map_acl_platform_prompt(raw_value: object) -> str:
    platform = str(raw_value or "").strip().lower()
    if not platform:
        raise ValidationError("platform is required")
    if platform not in ACL_PLATFORM_PROMPT_MAP:
        allowed = ", ".join(sorted(ACL_PLATFORM_PROMPT_MAP))
        raise ValidationError(f"platform must be one of: {allowed}")
    return ACL_PLATFORM_PROMPT_MAP[platform]


def validate_openai_model(raw_value: object) -> str | None:
    model = str(raw_value or "").strip()
    if not model:
        return None
    if model not in OPENAI_MODELS:
        allowed = ", ".join(sorted(OPENAI_MODELS))
        raise ValidationError(f"model must be one of: {allowed}")
    return model


def parse_acl_optimize_payload(payload: dict) -> tuple[str, str, str | None]:
    if payload is None:
        raise ValidationError("JSON payload is required")

    platform = validate_acl_platform(payload.get("platform"))
    model = validate_openai_model(payload.get("model"))
    current_acl = str(payload.get("current", "")).strip()
    if not current_acl:
        raise ValidationError("current is required")

    return platform, current_acl, model


def parse_acl_verify_payload(payload: dict) -> tuple[str, str, str]:
    if payload is None:
        raise ValidationError("JSON payload is required")

    platform = validate_acl_platform(payload.get("platform"))
    original_acl = str(payload.get("current", "")).strip()
    candidate_acl = str(payload.get("candidate", "")).strip()

    if not original_acl:
        raise ValidationError("current is required")
    if not candidate_acl:
        raise ValidationError("candidate is required")

    return platform, original_acl, candidate_acl


def parse_acl_generate_commands_payload(payload: dict) -> tuple[str, str, str, str | None]:
    if payload is None:
        raise ValidationError("JSON payload is required")

    mapped_platform = map_acl_platform_prompt(payload.get("platform"))
    model = validate_openai_model(payload.get("model"))
    current_acl = str(payload.get("current", "")).strip()
    candidate_acl = str(payload.get("candidate", "")).strip()

    if not current_acl:
        raise ValidationError("current is required")
    if not candidate_acl:
        raise ValidationError("candidate is required")

    return mapped_platform, current_acl, candidate_acl, model
