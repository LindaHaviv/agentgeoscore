"""Parse web-gates.sh JSON output, print a human report, exit 1 on any fail.

Hardened against malformed JSON / missing keys so a script error upstream
surfaces cleanly instead of stack-tracing in CI.
"""
import json
import sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"FATAL: gate script emitted non-JSON output: {e}", file=sys.stderr)
    print("Raw stdin was:", file=sys.stderr)
    sys.stdin.seek(0) if sys.stdin.seekable() else None
    sys.exit(2)

if not isinstance(data, dict) or "gates" not in data:
    print(f"FATAL: gate output missing 'gates' key: {data!r}", file=sys.stderr)
    sys.exit(2)

gates = data.get("gates")
if not isinstance(gates, list):
    print(f"FATAL: 'gates' is not a list: {gates!r}", file=sys.stderr)
    sys.exit(2)

fails: list[tuple[str, str, str]] = []
warns: list[tuple[str, str]] = []

print("\nWeb-gates CI run")
print("=" * 60)

if not gates:
    print("  (no gates ran — empty array)")
    print()
    print("FATAL: no gates produced output. Check web-gates.sh for early-exit", file=sys.stderr)
    sys.exit(2)

for g in gates:
    if not isinstance(g, dict):
        continue
    name = str(g.get("name", "")).strip()
    status = str(g.get("status", "")).strip()
    summary = str(g.get("summary", "")).strip()
    marker = {
        "pass": "PASS",
        "warn": "WARN",
        "fail": "FAIL",
        "skipped": "SKIP",
        "missing": "MISS",
        "info": "INFO",
    }.get(status, "?")
    print(f"  [{marker}] {name:26s} {summary}")
    if status == "fail":
        fails.append((name, summary, str(g.get("details", "")).strip()))
    elif status == "warn":
        warns.append((name, summary))
print()

if warns:
    print(f"{len(warns)} warning(s) (non-blocking):")
    for n, s in warns:
        print(f"  - {n}: {s}")
    print()

if fails:
    print(f"{len(fails)} failing gate(s) — blocking merge:")
    for n, s, d in fails:
        print(f"  - {n}: {s}")
        if d:
            for line in d.splitlines()[:10]:
                print(f"      {line}")
    sys.exit(1)

print("All blocking gates green.")
