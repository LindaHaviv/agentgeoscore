"""Read newline-delimited locale-file paths from stdin, report key drift.

Called by web-gates.sh. Lives as a separate file (vs an embedded `python3 -c`
heredoc) so we never interpolate shell-supplied filenames into a Python
string — which was a CWE-78 / CWE-95 hazard.
"""
import json
import sys
from pathlib import Path


def keys(obj: object, prefix: str = "") -> set[str]:
    """Flatten a nested dict into a set of dotted-path keys."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.add(p)
            out |= keys(v, p)
    return out


def load_keys(path: Path) -> set[str]:
    try:
        return keys(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  cannot read {path}: {e}", file=sys.stderr)
        return set()


def main() -> int:
    paths = [Path(line) for line in sys.stdin.read().splitlines() if line.strip()]
    if not paths:
        return 0  # nothing to check

    base = paths[0]
    base_keys = load_keys(base)
    if not base_keys:
        return 1

    drift_found = False
    for other in paths[1:]:
        other_keys = load_keys(other)
        missing_in_other = base_keys - other_keys
        extra_in_other = other_keys - base_keys
        if missing_in_other or extra_in_other:
            drift_found = True
            print(f"{other} drift vs {base}:")
            for k in sorted(missing_in_other)[:10]:
                print(f"  - missing: {k}")
            for k in sorted(extra_in_other)[:10]:
                print(f"  + extra:   {k}")

    return 1 if drift_found else 0


if __name__ == "__main__":
    sys.exit(main())
