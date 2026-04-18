import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Tuple


IP_NETWORK = ipaddress.IPv4Network | ipaddress.IPv6Network

# Extract IP-like tokens and rely on ipaddress for final validation.
IP_CANDIDATE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9A-Fa-f:.%]+(?:/\d{1,3})?)(?![0-9A-Za-z])")
IP_OR_HOST_RE = r"[0-9A-Fa-f:.%]+"
SUBNET_RE = r"(?:[0-9.]+|[0-9A-Fa-f:]+|\d{1,3})"
LINE_NETWORK_PATTERNS = [
    re.compile(rf"\baddress\s+(?P<ip>{IP_OR_HOST_RE})\s+(?P<subnet>{SUBNET_RE})\b", re.IGNORECASE),
    re.compile(rf"\bnetwork\s+(?P<ip>{IP_OR_HOST_RE})\s+mask\s+(?P<subnet>{SUBNET_RE})\b", re.IGNORECASE),
    re.compile(rf"\bnetwork\s+(?P<ip>{IP_OR_HOST_RE})\s+(?P<subnet>{SUBNET_RE})\b", re.IGNORECASE),
    re.compile(rf"\bip\s+(?P<ip>{IP_OR_HOST_RE})\s+(?P<subnet>{SUBNET_RE})\b", re.IGNORECASE),
]
ANY_TOKEN_MAP = {
    "any": "0.0.0.0/0",
    "any4": "0.0.0.0/0",
    "any6": "::/0",
}
ANY_TOKEN_RE = re.compile(r"\b(any6|any4|any)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCandidate:
    token: str
    start: int
    network: IP_NETWORK


def parse_search_network(value: str) -> IP_NETWORK:
    return ipaddress.ip_network(value, strict=False)


def _parse_candidate(token: str) -> IP_NETWORK | None:
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def _contains_index(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def iter_line_candidates(line: str) -> Iterator[ParsedCandidate]:
    consumed_spans: list[tuple[int, int]] = []

    for matcher in LINE_NETWORK_PATTERNS:
        for match in matcher.finditer(line):
            network_token = f"{match.group('ip')}/{match.group('subnet')}"
            parsed = _parse_candidate(network_token)
            if parsed is None:
                continue
            consumed_spans.append((match.start(), match.end()))
            yield ParsedCandidate(token=network_token, start=match.start("ip"), network=parsed)

    for match in ANY_TOKEN_RE.finditer(line):
        if _contains_index(match.start(), consumed_spans):
            continue
        token = match.group(1)
        parsed = _parse_candidate(ANY_TOKEN_MAP[token.lower()])
        if parsed is None:
            continue
        consumed_spans.append((match.start(), match.end()))
        yield ParsedCandidate(token=token, start=match.start(1), network=parsed)

    for match in IP_CANDIDATE_RE.finditer(line):
        if _contains_index(match.start(1), consumed_spans):
            continue
        token = match.group(1)
        parsed = _parse_candidate(token)
        if parsed is None:
            continue
        yield ParsedCandidate(token=token, start=match.start(1), network=parsed)


def build_line_matches(
    filename: str,
    line_number: int,
    line_text: str,
    search_network: IP_NETWORK,
) -> List[dict]:
    line_matches: List[dict] = []
    for candidate in iter_line_candidates(line_text):
        if candidate.network.version != search_network.version:
            continue
        if not search_network.subnet_of(candidate.network):
            continue

        line_matches.append(
            {
                "filename": filename,
                "line_number": line_number,
                "matched_object": candidate.token,
                "matched_network": str(candidate.network),
                "line": line_text,
                "capture": line_text[candidate.start :],
            }
        )

    return line_matches


def find_object_matches(
    search_input: str,
    files_with_lines: Iterable[Tuple[str, Iterable[Tuple[int, str]]]],
    max_results: int = 500,
) -> tuple[str, List[dict], bool]:
    search_network = parse_search_network(search_input)
    results: List[dict] = []
    truncated = False

    for filename, line_iter in files_with_lines:
        for line_number, line_text in line_iter:
            results.extend(build_line_matches(filename, line_number, line_text, search_network))
            if len(results) >= max_results:
                results = results[:max_results]
                truncated = True
                break
        if truncated:
            break

    results.sort(key=lambda row: (row["filename"], row["line_number"], row["matched_object"]))
    return str(search_network), results, truncated


def build_line_string_matches(
    filename: str,
    line_number: int,
    line_text: str,
    search_text: str,
) -> List[dict]:
    lowered_line = line_text.casefold()
    lowered_search = search_text.casefold()
    line_matches: List[dict] = []

    start = 0
    while True:
        index = lowered_line.find(lowered_search, start)
        if index < 0:
            break

        end = index + len(search_text)
        line_matches.append(
            {
                "filename": filename,
                "line_number": line_number,
                "matched_object": line_text[index:end],
                "line": line_text,
                "capture": line_text[index:],
            }
        )
        start = index + 1

    return line_matches


def find_string_matches(
    search_text: str,
    files_with_lines: Iterable[Tuple[str, Iterable[Tuple[int, str]]]],
    max_results: int = 500,
) -> tuple[str, List[dict], bool]:
    normalized = str(search_text or "").strip()
    if not normalized:
        raise ValueError("find_text is required")

    results: List[dict] = []
    truncated = False

    for filename, line_iter in files_with_lines:
        for line_number, line_text in line_iter:
            results.extend(build_line_string_matches(filename, line_number, line_text, normalized))
            if len(results) >= max_results:
                results = results[:max_results]
                truncated = True
                break
        if truncated:
            break

    results.sort(key=lambda row: (row["filename"], row["line_number"], row["matched_object"]))
    return normalized, results, truncated


def normalize_max_results(raw_value: object, default: int = 500, max_allowed: int = 10000) -> int:
    if raw_value in {None, ""}:
        return default
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("max_results must be an integer") from exc

    if parsed < 1:
        raise ValueError("max_results must be greater than 0")
    if parsed > max_allowed:
        return max_allowed
    return parsed
