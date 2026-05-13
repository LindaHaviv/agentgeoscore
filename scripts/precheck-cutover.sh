#!/usr/bin/env bash
# Pre-merge cutover gate for the agentgeoscore.com / api.agentgeoscore.com
# domain switch. Run this BEFORE merging the cutover PR to catch the
# deploy-ordering hazard where the new domain isn't yet resolvable —
# merging that state would publish broken OG image URLs everywhere.
#
# Exits non-zero if any of the production endpoints fail their health
# check. Safe to re-run; reports each check independently.
set -euo pipefail

FRONTEND="${1:-https://agentgeoscore.com}"
BACKEND="${2:-https://api.agentgeoscore.com}"

pass=0
fail=0

check() {
  local label="$1"
  local cmd="$2"
  if eval "$cmd"; then
    printf "  \033[32m✓\033[0m %s\n" "$label"
    pass=$((pass + 1))
  else
    printf "  \033[31m✗\033[0m %s\n" "$label"
    fail=$((fail + 1))
  fi
}

echo "Cutover precheck:"
echo "  frontend: $FRONTEND"
echo "  backend:  $BACKEND"
echo

echo "DNS resolution"
check "frontend host resolves" "host -W 5 \"${FRONTEND#https://}\" >/dev/null 2>&1"
check "backend host resolves"  "host -W 5 \"${BACKEND#https://}\"  >/dev/null 2>&1"
echo

echo "TLS + reachability"
check "frontend returns 2xx/3xx on /" \
  "curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 \"$FRONTEND/\" | grep -qE '^(2|3)'"
check "backend health endpoint is 200" \
  "curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 \"$BACKEND/api/healthz\" | grep -q '^200$'"
echo

echo "OG image endpoint (1200x630 PNG)"
tmp_og=$(mktemp -t og-precheck.XXXXXX.png)
trap 'rm -f "$tmp_og"' EXIT
check "OG endpoint returns image/png" \
  "curl -sS -o \"$tmp_og\" -w '%{content_type}\n' --max-time 15 \"$BACKEND/api/og?brand=1\" | grep -q '^image/png'"
check "OG PNG file is > 25 KB (font rendering working)" \
  "[ \"\$(wc -c <\"$tmp_og\")\" -gt 25600 ]"
echo

echo "Share route HTML"
check "share route includes og:image meta" \
  "curl -sS --max-time 10 \"$BACKEND/share?d=stripe.com&s=94&g=A\" | grep -q 'og:image'"
echo

echo "Summary: $pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then
  echo "DO NOT MERGE — fix the failing endpoints before flipping production."
  exit 1
fi
echo "All cutover gates green — safe to merge."
