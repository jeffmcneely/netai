import ipaddress
import re
from typing import List


FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


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
