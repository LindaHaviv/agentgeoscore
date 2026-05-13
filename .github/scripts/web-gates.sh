#!/usr/bin/env bash
# Run a web project's PR gate tests and emit structured JSON to stdout.
#
# Auto-discovers gates by inspecting the project layout. Gates that need
# external tools (xmllint, html-validate, lhci) are run when the tool is
# available and gracefully skipped otherwise.
#
# Gates:
#   1. predict_self_score       — full /api/scan simulation (project-specific)
#   2. seo_shell                — vitest seo-shell.test.ts (project-specific)
#   3. accessibility            — Playwright axe spec (project-specific)
#   4. bundle_size              — gzip size of main JS chunk (universal)
#   5. readme_test_count        — README test count vs pytest reality (universal)
#   6. hardcoded_preview_domain — git grep for *.devinapps.com / vercel.app etc.
#   7. xml_validity             — xmllint --noout over every .xml in diff (v1.1)
#   8. html_validity            — html-validate over generated dist HTML (v1.1)
#   9. security_txt             — frontend/public/.well-known/security.txt? (v1.1)
#  10. locale_parity            — translation-key drift between locale files (v1.1)
#  11. lighthouse               — lhci autorun if config present (v1.1)
#
# Usage:
#   web-gates.sh [--project-root /path/to/repo]
#   web-gates.sh --pretty           # pipe-friendly human-readable
#
# Output: JSON object with one entry per gate.

set -uo pipefail

PROJECT_ROOT="${PWD}"
PRETTY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --pretty) PRETTY=1; shift ;;
    *) shift ;;
  esac
done

cd "$PROJECT_ROOT" || { echo '{"error":"bad project root"}'; exit 0; }

# JSON-escape a string by piping through python.
json_escape() {
  python3 -c 'import sys,json;print(json.dumps(sys.stdin.read()), end="")' <<<"$1"
}

emit_gate() {
  local name="$1" status="$2" summary="$3" details="$4"
  printf '{"name":%s,"status":%s,"summary":%s,"details":%s}' \
    "$(json_escape "$name")" \
    "$(json_escape "$status")" \
    "$(json_escape "$summary")" \
    "$(json_escape "$details")"
}

gates=()

# ─── 1. predict_self_score ────────────────────────────────────────────────
if [[ -f backend/tests/test_predict_self_score.py ]]; then
  if pushd backend >/dev/null 2>&1; then
    out=$(uv run --extra dev pytest tests/test_predict_self_score.py -q --tb=line 2>&1)
    rc=$?
    popd >/dev/null
    if [[ $rc -eq 0 ]]; then
      gates+=("$(emit_gate predict_self_score pass "Full /api/scan pipeline returns 100/A on rebuilt dist" "$out")")
    else
      gates+=("$(emit_gate predict_self_score fail "Self-score regression detected" "$out")")
    fi
  fi
else
  gates+=("$(emit_gate predict_self_score missing "No predict-self-score gate found" "Add backend/tests/test_predict_self_score.py or equivalent.")")
fi

# ─── 2. seo_shell ─────────────────────────────────────────────────────────
if [[ -f frontend/src/test/seo-shell.test.ts ]]; then
  if pushd frontend >/dev/null 2>&1; then
    if [[ ! -d node_modules ]]; then npm ci >/dev/null 2>&1; fi
    out=$(npm test -- --run src/test/seo-shell.test.ts 2>&1)
    rc=$?
    popd >/dev/null
    if [[ $rc -eq 0 ]]; then
      gates+=("$(emit_gate seo_shell pass "SEO shell assertions all pass" "$out")")
    else
      gates+=("$(emit_gate seo_shell fail "SEO shell regression detected" "$out")")
    fi
  fi
else
  gates+=("$(emit_gate seo_shell missing "No seo-shell test found" "Add a vitest spec that parses index.html and asserts JSON-LD types, h1, landmarks, byline, citation density.")")
fi

# ─── 3. accessibility ─────────────────────────────────────────────────────
if [[ -f frontend/tests/e2e/a11y.spec.ts ]]; then
  gates+=("$(emit_gate accessibility skipped "axe-core spec present; run manually with: cd frontend && npm run test:e2e -- a11y.spec.ts" "")")
else
  gates+=("$(emit_gate accessibility missing "No axe-core a11y spec found" "Add frontend/tests/e2e/a11y.spec.ts with @axe-core/playwright.")")
fi

# ─── 4. bundle_size ───────────────────────────────────────────────────────
if [[ -d frontend/dist ]]; then
  main_js=$(find frontend/dist/assets -name 'index-*.js' -type f 2>/dev/null | head -1)
  if [[ -n "$main_js" ]]; then
    gz_bytes=$(gzip -c "$main_js" | wc -c | tr -d ' ')
    gz_kb=$((gz_bytes / 1024))
    if (( gz_kb > 250 )); then
      gates+=("$(emit_gate bundle_size fail "Main JS chunk ${gz_kb} KB gzipped — over 250 KB budget" "$main_js")")
    else
      gates+=("$(emit_gate bundle_size pass "Main JS chunk ${gz_kb} KB gzipped (under 250 KB budget)" "$main_js")")
    fi
  else
    gates+=("$(emit_gate bundle_size missing "frontend/dist has no index-*.js — run npm run build first" "")")
  fi
else
  gates+=("$(emit_gate bundle_size missing "No frontend/dist build output found" "Run: cd frontend && npm run build")")
fi

# ─── 5. readme_test_count ────────────────────────────────────────────────
# More forgiving regex than v1 — accepts "backend, NNN tests" or "(backend, NNN tests".
if [[ -f README.md ]]; then
  readme_count=$(grep -oE '\(backend,?\s+[0-9]+\s+tests?' README.md | grep -oE '[0-9]+' | head -1)
  if [[ -z "$readme_count" ]]; then
    readme_count=$(grep -oE 'backend,?\s+[0-9]+\s+tests?' README.md | grep -oE '[0-9]+' | head -1)
  fi
  actual_count=""
  if [[ -d backend ]]; then
    # `pytest --collect-only -q` outputs per-file counts but no grand total.
    # Drop `-q` to get the "NNN tests collected" line.
    actual_count=$(cd backend && uv run --extra dev pytest --collect-only 2>/dev/null | grep -oE '[0-9]+ tests? collected' | grep -oE '^[0-9]+' | head -1)
  fi
  if [[ -n "$readme_count" && -n "$actual_count" ]]; then
    if [[ "$readme_count" == "$actual_count" ]]; then
      gates+=("$(emit_gate readme_test_count pass "README claims ${readme_count} tests; pytest collected ${actual_count}" "")")
    else
      gates+=("$(emit_gate readme_test_count fail "README drift: claims ${readme_count} tests, pytest collected ${actual_count}" "")")
    fi
  else
    gates+=("$(emit_gate readme_test_count skipped "Couldn't extract test count from README (${readme_count:-none}) or pytest (${actual_count:-none})" "")")
  fi
fi

# ─── 6. hardcoded_preview_domain ─────────────────────────────────────────
PREVIEW_PATTERNS='devinapps\.com|vercel\.app|netlify\.app|\.fly\.dev|pages\.dev'
leaks=$(git grep -lE "$PREVIEW_PATTERNS" -- \
  ':!**/CHANGELOG.md' ':!**/README.md' ':!**/SECURITY.md' ':!**/CONTRIBUTING.md' \
  ':!**/docs/**' ':!**/launch-copy*' ':!**/.agents/**' \
  2>/dev/null || true)
if [[ -n "$leaks" ]]; then
  gates+=("$(emit_gate hardcoded_preview_domain warn "Preview / branch URLs hardcoded in source — should be env-driven" "$leaks")")
else
  gates+=("$(emit_gate hardcoded_preview_domain pass "No preview-domain hardcoding outside docs" "")")
fi

# ─── 7. xml_validity (v1.1) ──────────────────────────────────────────────
# Validate every .xml file's namespace + parse via xmllint.
xml_files=$(git ls-files '*.xml' 2>/dev/null || find . -name '*.xml' -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/.git/*' 2>/dev/null)
if [[ -n "$xml_files" ]]; then
  if command -v xmllint >/dev/null 2>&1; then
    xml_errors=""
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      err=$(xmllint --noout "$f" 2>&1)
      if [[ $? -ne 0 ]]; then
        xml_errors="${xml_errors}${f}: ${err}\n"
      fi
      # Catch the common sitemap namespace typo (sitemap.org vs sitemaps.org).
      if grep -qE 'xmlns="https?://www\.sitemap\.org' "$f"; then
        xml_errors="${xml_errors}${f}: wrong sitemap xmlns — should be www.sitemaps.org (plural)\n"
      fi
    done <<< "$xml_files"
    if [[ -n "$xml_errors" ]]; then
      gates+=("$(emit_gate xml_validity fail "XML validity / namespace errors" "$(printf "$xml_errors")")")
    else
      file_count=$(echo "$xml_files" | wc -l | tr -d ' ')
      gates+=("$(emit_gate xml_validity pass "${file_count} XML file(s) parse cleanly with correct namespaces" "")")
    fi
  else
    gates+=("$(emit_gate xml_validity skipped "xmllint not installed (preinstalled on macOS; on Linux: apt install libxml2-utils)" "")")
  fi
else
  gates+=("$(emit_gate xml_validity skipped "No XML files in project" "")")
fi

# ─── 8. html_validity (v1.1) ─────────────────────────────────────────────
# Run W3C Nu HTML Checker (via html-validate or vnu-jar) against built HTML.
if [[ -d frontend/dist ]]; then
  html_files=$(find frontend/dist -maxdepth 2 -name '*.html' 2>/dev/null | head -5)
  if [[ -n "$html_files" ]] && command -v npx >/dev/null 2>&1; then
    # Use html-validate if available locally; otherwise skip with install hint.
    if [[ -f frontend/node_modules/.bin/html-validate ]] || npm ls -g html-validate >/dev/null 2>&1; then
      cd frontend
      out=$(npx html-validate dist/*.html 2>&1)
      rc=$?
      cd ..
      if [[ $rc -eq 0 ]]; then
        gates+=("$(emit_gate html_validity pass "Built HTML passes html-validate" "$out")")
      else
        gates+=("$(emit_gate html_validity warn "html-validate found issues" "$out")")
      fi
    else
      gates+=("$(emit_gate html_validity skipped "html-validate not installed (cd frontend && npm i -D html-validate)" "")")
    fi
  else
    gates+=("$(emit_gate html_validity skipped "No frontend/dist/*.html or npx not available" "")")
  fi
else
  gates+=("$(emit_gate html_validity skipped "No frontend/dist build output" "")")
fi

# ─── 9. security_txt (v1.1) ──────────────────────────────────────────────
# RFC 9116 — every public-facing site should publish /.well-known/security.txt.
security_paths=(
  "frontend/public/.well-known/security.txt"
  "frontend/public/security.txt"
  "public/.well-known/security.txt"
  "static/.well-known/security.txt"
)
found_security=""
for p in "${security_paths[@]}"; do
  if [[ -f "$p" ]]; then
    found_security="$p"
    break
  fi
done
if [[ -n "$found_security" ]]; then
  # Check for required + recommended RFC 9116 fields.
  body=$(cat "$found_security")
  missing=""
  [[ "$body" != *"Contact:"* ]] && missing="${missing} Contact"
  [[ "$body" != *"Expires:"* ]] && missing="${missing} Expires"
  if [[ -n "$missing" ]]; then
    gates+=("$(emit_gate security_txt warn "security.txt present but missing required field(s):${missing}" "$found_security")")
  else
    gates+=("$(emit_gate security_txt pass "security.txt at ${found_security} has Contact + Expires" "")")
  fi
else
  if [[ -f "SECURITY.md" ]]; then
    gates+=("$(emit_gate security_txt warn "SECURITY.md present but no /.well-known/security.txt — bots can't auto-discover" "Add frontend/public/.well-known/security.txt per RFC 9116 with Contact: and Expires: fields.")")
  else
    gates+=("$(emit_gate security_txt missing "No security.txt and no SECURITY.md" "Add a vulnerability-disclosure policy.")")
  fi
fi

# ─── 10. locale_parity (v1.1) ─────────────────────────────────────────────
# If the project has i18n locale files, check that keys match between locales.
locale_files=$(find . -type f \( -path '*locales/*.json' -o -path '*i18n/*.json' -o -path '*messages/*.json' -o -path '*lang/*.json' \) -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/.git/*' 2>/dev/null | sort)
if [[ -n "$locale_files" ]]; then
  # Use the first locale file as the base and compare keys with the others.
  base=$(echo "$locale_files" | head -1)
  base_keys=$(python3 -c "
import json, sys
try:
    with open('$base') as f:
        d = json.load(f)
    def keys(obj, prefix=''):
        out = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f'{prefix}.{k}' if prefix else k
                out.add(p)
                out |= keys(v, p)
        return out
    print('\n'.join(sorted(keys(d))))
except Exception as e:
    print(f'ERR:{e}', file=sys.stderr)
" 2>&1)
  drift=""
  while IFS= read -r f; do
    [[ -z "$f" || "$f" == "$base" ]] && continue
    other_keys=$(python3 -c "
import json
with open('$f') as fp:
    d = json.load(fp)
def keys(obj, prefix=''):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f'{prefix}.{k}' if prefix else k
            out.add(p)
            out |= keys(v, p)
    return out
print('\n'.join(sorted(keys(d))))
" 2>/dev/null)
    diff_out=$(diff <(echo "$base_keys") <(echo "$other_keys") 2>/dev/null | head -10)
    if [[ -n "$diff_out" ]]; then
      drift="${drift}${f}:\n${diff_out}\n"
    fi
  done <<< "$locale_files"
  if [[ -n "$drift" ]]; then
    gates+=("$(emit_gate locale_parity warn "Locale key drift detected vs base ${base}" "$(printf "$drift")")")
  else
    locale_count=$(echo "$locale_files" | wc -l | tr -d ' ')
    gates+=("$(emit_gate locale_parity pass "${locale_count} locale file(s) have matching keys" "")")
  fi
else
  gates+=("$(emit_gate locale_parity skipped "No i18n locale files found" "")")
fi

# ─── 11. lighthouse (v1.1, opt-in) ────────────────────────────────────────
if [[ -f frontend/lighthouserc.json ]] || [[ -f frontend/.lighthouserc.json ]] || [[ -f lighthouserc.json ]]; then
  if command -v lhci >/dev/null 2>&1; then
    gates+=("$(emit_gate lighthouse skipped "Lighthouse CI config found but skipped (heavy, run manually: cd frontend && lhci autorun)" "")")
  else
    gates+=("$(emit_gate lighthouse skipped "Lighthouse CI config found but lhci not installed (npm i -g @lhci/cli)" "")")
  fi
else
  gates+=("$(emit_gate lighthouse missing "No Lighthouse CI config — consider adding frontend/lighthouserc.json with thresholds for Perf/SEO/A11y/Best-Practices" "")")
fi

# ─── Join gates and emit ──────────────────────────────────────────────────
gates_json=""
for g in "${gates[@]}"; do
  if [[ -z "$gates_json" ]]; then
    gates_json="$g"
  else
    gates_json="${gates_json},${g}"
  fi
done

result=$(printf '{"project_root":%s,"gates":[%s]}\n' \
  "$(json_escape "$PROJECT_ROOT")" \
  "$gates_json")

if [[ "$PRETTY" == "1" ]]; then
  echo "$result" | python3 -c '
import json, sys
r = json.load(sys.stdin)
root = r["project_root"].strip()
print("\nWeb-gates report for " + root)
print("-" * 60)
for g in r["gates"]:
    status = g["status"].strip()
    name = g["name"].strip()
    summary = g["summary"].strip()
    marker = {"pass":"PASS","warn":"WARN","fail":"FAIL","skipped":"SKIP","missing":"MISS"}.get(status, "?")
    print(f"  [{marker}] {name:26s} {summary}")
print()
'
else
  echo "$result"
fi
