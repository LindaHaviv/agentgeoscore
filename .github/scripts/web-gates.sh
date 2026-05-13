#!/usr/bin/env bash
# Run a web project's PR gate tests and emit structured JSON to stdout.
#
# Auto-discovers gates by inspecting the project layout. Gates that need
# external tools (xmllint, html-validate, lhci) are run when the tool is
# available and gracefully skipped otherwise.
#
# Gates (status: pass | warn | fail | skipped | missing | info):
#   1. predict_self_score       — full /api/scan simulation (project-specific)
#   2. seo_shell                — vitest seo-shell.test.ts (project-specific)
#   3. accessibility            — Playwright axe spec (project-specific)
#   4. bundle_size              — gzip size of main JS chunk (universal)
#   5. readme_test_count        — README test count vs pytest reality (universal)
#   6. hardcoded_preview_domain — git grep for *.devinapps.com / vercel.app etc.
#   7. xml_validity             — xmllint --noout over every .xml in diff
#   8. html_validity            — html-validate over generated dist HTML
#   9. security_txt             — frontend/public/.well-known/security.txt? (RFC 9116)
#  10. locale_parity            — translation-key drift between locale files
#  11. lighthouse               — lhci autorun if config present
#
# Usage:
#   web-gates.sh [--project-root /path/to/repo]
#   web-gates.sh --pretty           # pipe-friendly human-readable
#
# Output: JSON object with one entry per gate.
#
# Notes:
#   - This script intentionally does NOT use `set -e`. Each gate captures its
#     own exit codes explicitly because we want one gate's failure to surface
#     as a `fail` status, not abort the whole script.
#   - `set -uo pipefail` is on so unset variables and broken pipes surface.

set -uo pipefail

# ─── arg parsing + project-root validation ─────────────────────────────────

PROJECT_ROOT="${PWD}"
PRETTY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      if [[ -z "${2:-}" ]]; then
        printf '{"error":"--project-root requires a path","gates":[]}\n'
        exit 2
      fi
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --pretty) PRETTY=1; shift ;;
    *) shift ;;
  esac
done

# Resolve to absolute path and validate.
if ! PROJECT_ROOT=$(cd "$PROJECT_ROOT" 2>/dev/null && pwd); then
  printf '{"error":"project root does not exist or is not a directory","gates":[]}\n'
  exit 2
fi
# Heuristic: a project root has either .git or a recognised manifest. Prevents
# accidental --project-root=/ or --project-root=/etc walks.
if [[ ! -d "$PROJECT_ROOT/.git" ]] \
   && [[ ! -f "$PROJECT_ROOT/package.json" ]] \
   && [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]] \
   && [[ ! -f "$PROJECT_ROOT/Cargo.toml" ]] \
   && [[ ! -f "$PROJECT_ROOT/go.mod" ]]; then
  printf '{"error":"project root does not look like a project (no .git/package.json/pyproject.toml/Cargo.toml/go.mod)","gates":[]}\n'
  exit 2
fi

cd "$PROJECT_ROOT"

# ─── helpers ───────────────────────────────────────────────────────────────

# JSON-escape a string. Reads via env to avoid shell-quoting / command-injection
# hazards from arbitrary content.
json_escape() {
  V="$1" python3 -c 'import os,json,sys; sys.stdout.write(json.dumps(os.environ["V"]))'
}

emit_gate() {
  local name="$1" status="$2" summary="$3" details="$4"
  printf '{"name":%s,"status":%s,"summary":%s,"details":%s}' \
    "$(json_escape "$name")" \
    "$(json_escape "$status")" \
    "$(json_escape "$summary")" \
    "$(json_escape "$details")"
}

# Run a command and capture both exit code and output safely. Usage:
#   run_capture out rc -- some command --with args
# After: $out is stdout+stderr, $rc is the exit code.
run_capture() {
  local _out_var="$1" _rc_var="$2"
  shift 2
  [[ "$1" == "--" ]] && shift
  local _out
  _out=$("$@" 2>&1)
  local _rc=$?
  printf -v "$_out_var" '%s' "$_out"
  printf -v "$_rc_var" '%d' "$_rc"
}

gates=()

# ─── 1. predict_self_score ────────────────────────────────────────────────
# Subshell pattern (`out=$( cd dir && cmd )`) is strictly more bulletproof
# than pushd/popd: the parent's cwd is unaffected regardless of what the
# subshell does, even if the subprocess crashes or changes directory
# itself. No popd to remember, no cwd-leak risk for subsequent gates.
if [[ -f backend/tests/test_predict_self_score.py ]]; then
  pred_out=$(cd backend && uv run --extra dev pytest tests/test_predict_self_score.py -q --tb=line 2>&1)
  pred_rc=$?
  if [[ $pred_rc -eq 0 ]]; then
    gates+=("$(emit_gate predict_self_score pass "Full /api/scan pipeline returns 100/A on rebuilt dist" "$pred_out")")
  else
    gates+=("$(emit_gate predict_self_score fail "Self-score regression detected (or pytest didn't run cleanly)" "$pred_out")")
  fi
else
  gates+=("$(emit_gate predict_self_score missing "No predict-self-score gate found" "Add backend/tests/test_predict_self_score.py or equivalent.")")
fi

# ─── 2. seo_shell ─────────────────────────────────────────────────────────
if [[ -f frontend/src/test/seo-shell.test.ts ]]; then
  seo_out=$(
    cd frontend || exit 1
    [[ -d node_modules ]] || npm ci >/dev/null 2>&1 || true
    npm test -- --run src/test/seo-shell.test.ts 2>&1
  )
  seo_rc=$?
  if [[ $seo_rc -eq 0 ]]; then
    gates+=("$(emit_gate seo_shell pass "SEO shell assertions all pass" "$seo_out")")
  else
    gates+=("$(emit_gate seo_shell fail "SEO shell regression detected" "$seo_out")")
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
if [[ -f README.md ]]; then
  readme_count=$(grep -oE '\(backend,?\s+[0-9]+\s+tests?' README.md | grep -oE '[0-9]+' | head -1)
  if [[ -z "$readme_count" ]]; then
    readme_count=$(grep -oE 'backend,?\s+[0-9]+\s+tests?' README.md | grep -oE '[0-9]+' | head -1)
  fi
  actual_count=""
  if [[ -d backend ]]; then
    # Drop `-q` so pytest emits the grand total line. Subshell scopes the cd.
    actual_count=$(
      cd backend && uv run --extra dev pytest --collect-only 2>/dev/null \
        | grep -oE '[0-9]+ tests? collected' \
        | grep -oE '^[0-9]+' \
        | head -1
    )
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
# If the project has a Vite plugin / build step that rewrites the domain at
# build time, downgrade WARN → INFO. We detect that by grepping for
# `VITE_FRONTEND_ORIGIN` in a vite.config or similar.
PREVIEW_PATTERNS='devinapps\.com|vercel\.app|netlify\.app|\.fly\.dev|pages\.dev'
leaks=$(git grep -lE "$PREVIEW_PATTERNS" -- \
  ':!**/CHANGELOG.md' ':!**/README.md' ':!**/SECURITY.md' ':!**/CONTRIBUTING.md' \
  ':!**/docs/**' ':!**/launch-copy*' ':!**/.agents/**' \
  2>/dev/null || true)
has_env_cutover=0
if git grep -lE 'VITE_FRONTEND_ORIGIN|FRONTEND_ORIGIN' -- '**/vite.config.*' '**/build*' 2>/dev/null | grep -q .; then
  has_env_cutover=1
fi
if [[ -n "$leaks" ]]; then
  if [[ "$has_env_cutover" -eq 1 ]]; then
    gates+=("$(emit_gate hardcoded_preview_domain info "Source files contain preview-domain default (build pipeline rewrites via VITE_FRONTEND_ORIGIN; this is by design)" "$leaks")")
  else
    gates+=("$(emit_gate hardcoded_preview_domain warn "Preview / branch URLs hardcoded in source — should be env-driven" "$leaks")")
  fi
else
  gates+=("$(emit_gate hardcoded_preview_domain pass "No preview-domain hardcoding outside docs" "")")
fi

# ─── 7. xml_validity ─────────────────────────────────────────────────────
xml_files=$(git ls-files '*.xml' 2>/dev/null || find . -name '*.xml' -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/.git/*' 2>/dev/null)
if [[ -n "$xml_files" ]]; then
  if command -v xmllint >/dev/null 2>&1; then
    xml_errors=""
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      # Capture xmllint's rc EXPLICITLY — `$?` after later commands would be racey.
      xml_err=$(xmllint --noout "$f" 2>&1)
      xml_rc=$?
      if [[ $xml_rc -ne 0 ]]; then
        xml_errors+="${f}: ${xml_err}"$'\n'
      fi
      # Common typo: www.sitemap.org (singular) instead of www.sitemaps.org.
      if grep -qE 'xmlns="https?://www\.sitemap\.org' "$f"; then
        xml_errors+="${f}: wrong sitemap xmlns — should be www.sitemaps.org (plural)"$'\n'
      fi
    done <<< "$xml_files"
    if [[ -n "$xml_errors" ]]; then
      gates+=("$(emit_gate xml_validity fail "XML validity / namespace errors" "$xml_errors")")
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

# ─── 8. html_validity ─────────────────────────────────────────────────────
if [[ -d frontend/dist ]]; then
  html_files=$(find frontend/dist -maxdepth 2 -name '*.html' 2>/dev/null | head -5)
  if [[ -n "$html_files" ]] && command -v npx >/dev/null 2>&1; then
    if [[ -f frontend/node_modules/.bin/html-validate ]] || npm ls -g html-validate >/dev/null 2>&1; then
      # Subshell scopes the cd — no risk of leaking cwd into subsequent gates
      # if html-validate exits non-zero or somehow changes directory itself.
      hv_out=$(cd frontend && npx html-validate dist/*.html 2>&1)
      hv_rc=$?
      if [[ $hv_rc -eq 0 ]]; then
        gates+=("$(emit_gate html_validity pass "Built HTML passes html-validate" "$hv_out")")
      else
        gates+=("$(emit_gate html_validity warn "html-validate found issues" "$hv_out")")
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

# ─── 9. security_txt ──────────────────────────────────────────────────────
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

# ─── 10. locale_parity ────────────────────────────────────────────────────
# Implemented via a separate Python helper so we never embed shell-supplied
# filenames into a `python3 -c` string (CWE-78 hazard).
locale_files=$(find . -type f \( -path '*locales/*.json' -o -path '*i18n/*.json' -o -path '*messages/*.json' -o -path '*lang/*.json' \) -not -path '*/node_modules/*' -not -path '*/dist/*' -not -path '*/.git/*' 2>/dev/null | sort)
if [[ -n "$locale_files" ]]; then
  helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/locale-parity.py"
  if [[ -f "$helper" ]]; then
    parity_out=$(echo "$locale_files" | python3 "$helper" 2>&1)
    parity_rc=$?
    if [[ $parity_rc -eq 0 ]]; then
      locale_count=$(echo "$locale_files" | wc -l | tr -d ' ')
      gates+=("$(emit_gate locale_parity pass "${locale_count} locale file(s) have matching keys" "")")
    else
      gates+=("$(emit_gate locale_parity warn "Locale key drift detected" "$parity_out")")
    fi
  else
    gates+=("$(emit_gate locale_parity skipped "locale-parity.py helper not found next to web-gates.sh" "")")
  fi
else
  gates+=("$(emit_gate locale_parity skipped "No i18n locale files found" "")")
fi

# ─── 11. lighthouse (opt-in) ──────────────────────────────────────────────
if [[ -f frontend/lighthouserc.json ]] || [[ -f frontend/.lighthouserc.json ]] || [[ -f lighthouserc.json ]]; then
  if command -v lhci >/dev/null 2>&1; then
    gates+=("$(emit_gate lighthouse skipped "Lighthouse CI config found but skipped (heavy, run manually: cd frontend && lhci autorun)" "")")
  else
    gates+=("$(emit_gate lighthouse skipped "Lighthouse CI config found but lhci not installed (npm i -g @lhci/cli)" "")")
  fi
else
  gates+=("$(emit_gate lighthouse missing "No Lighthouse CI config — consider adding frontend/lighthouserc.json with thresholds for Perf/SEO/A11y/Best-Practices" "")")
fi

# ─── Join + emit ──────────────────────────────────────────────────────────
# Defensive: if no gates produced output (every check missing / skipped at
# a level that never appends), emit an explicit error gate so downstream
# parsers see something actionable rather than an empty array. (`[]` is
# valid JSON but signals "nothing ran" — which is itself worth a clear
# message.)
if [[ ${#gates[@]} -eq 0 ]]; then
  gates+=("$(emit_gate _meta error "No gates produced output — check script logic and project layout" "$PROJECT_ROOT")")
fi

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
    marker = {"pass":"PASS","warn":"WARN","fail":"FAIL","skipped":"SKIP","missing":"MISS","info":"INFO"}.get(status, "?")
    print(f"  [{marker}] {name:26s} {summary}")
print()
'
else
  echo "$result"
fi
