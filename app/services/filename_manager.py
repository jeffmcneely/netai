from typing import Set, Tuple


def split_basename_ext(filename: str) -> Tuple[str, str]:
    if filename.startswith(".") and filename.count(".") == 1:
        return filename, ""

    if "." not in filename:
        return filename, ""

    basename, ext = filename.rsplit(".", 1)
    return basename, ext


def resolve_conflict_name(filename: str, existing: Set[str], max_ordinal: int = 1000) -> Tuple[str, bool]:
    if filename not in existing:
        return filename, False

    basename, ext = split_basename_ext(filename)
    for ordinal in range(1, max_ordinal + 1):
        if ext:
            candidate = f"{basename}.{ordinal}.{ext}"
        else:
            candidate = f"{basename}.{ordinal}"
        if candidate not in existing:
            return candidate, True

    raise RuntimeError("Could not resolve filename conflict")
