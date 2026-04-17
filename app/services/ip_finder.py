import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Tuple


IP_NETWORK = ipaddress.IPv4Network | ipaddress.IPv6Network

# Extract IP-like tokens and rely on ipaddress for final validation.
IP_CANDIDATE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9A-Fa-f:.%]+(?:/\d{1,3})?)(?![0-9A-Za-z])")


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


def iter_line_candidates(line: str) -> Iterator[ParsedCandidate]:
    for match in IP_CANDIDATE_RE.finditer(line):
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
