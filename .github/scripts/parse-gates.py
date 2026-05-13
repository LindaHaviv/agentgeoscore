"""Parse web-gates.sh JSON output, print a human report, exit 1 on any fail."""
import json
import sys

data = json.load(sys.stdin)
fails: list[tuple[str, str, str]] = []
warns: list[tuple[str, str]] = []

print("\nWeb-gates CI run")
print("=" * 60)
for g in data["gates"]:
    name = g["name"].strip()
    status = g["status"].strip()
    summary = g["summary"].strip()
    marker = {
        "pass": "PASS",
        "warn": "WARN",
        "fail": "FAIL",
        "skipped": "SKIP",
        "missing": "MISS",
    }.get(status, "?")
    print(f"  [{marker}] {name:26s} {summary}")
    if status == "fail":
        fails.append((name, summary, g.get("details", "").strip()))
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
        print(f"  ✗ {n}: {s}")
        if d:
            for line in d.splitlines()[:10]:
                print(f"      {line}")
    sys.exit(1)

print("All blocking gates green.")
