#!/usr/bin/env bash
# CI wrapper: runs web-gates.sh, pipes the JSON to parse-gates.py, fails
# the build if any gate returned `fail`. `warn` and `skipped` are reported
# but don't block.

set -uo pipefail

cd "$(dirname "$0")/../.."  # repo root

./.github/scripts/web-gates.sh --project-root "$PWD" \
  | python3 ./.github/scripts/parse-gates.py
