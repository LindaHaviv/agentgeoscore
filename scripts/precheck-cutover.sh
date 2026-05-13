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
# Verify dimensions match what index.html declares (og:image:width/height).
# A 1200x630 declaration with a different actual size produces stretched
# previews everywhere it's embedded. Uses Python+PIL (already a backend dep)
# falling back to `file` if PIL isn't on PATH.
if command -v python3 >/dev/null 2>&1 && python3 -c "from PIL import Image" 2>/dev/null; then
  check "OG PNG dimensions are 1200x630" \
    "python3 -c 'from PIL import Image; w,h = Image.open(\"$tmp_og\").size; exit(0 if (w,h) == (1200,630) else 1)'"
elif command -v file >/dev/null 2>&1; then
  check "OG PNG dimensions are 1200x630 (via \`file\`)" \
    "file \"$tmp_og\" | grep -q '1200 x 630'"
fi
echo

echo "Share route HTML"
tmp_share=$(mktemp -t share-precheck.XXXXXX.html)
trap 'rm -f "$tmp_og" "$tmp_share"' EXIT
curl -sS --max-time 10 -o "$tmp_share" "$BACKEND/share?d=stripe.com&s=94&g=A" || true
check "share route includes og:image meta" \
  "grep -q 'og:image' \"$tmp_share\""
# Catch the case where FRONTEND_ORIGIN Fly secret wasn't updated — the
# meta-refresh would still point at the legacy host even with new code
# deployed. Anchor on the absolute URL form so it's unambiguous.
check "share route meta-refresh points at agentgeoscore.com (not legacy)" \
  "grep -qE 'https?://(www\\.)?agentgeoscore\\.com' \"$tmp_share\""
check "share route does NOT reference legacy devinapps URL" \
  "! grep -q 'devinapps.com' \"$tmp_share\""
echo

echo "Summary: $pass passed, $fail failed"
if [ "$fail" -gt 0 ]; then
  echo "DO NOT MERGE — fix the failing endpoints before flipping production."
  exit 1
fi
echo "All cutover gates green — safe to merge."
