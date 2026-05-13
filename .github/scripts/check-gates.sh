#!/usr/bin/env bash
# CI wrapper: runs web-gates.sh, pipes the JSON to parse-gates.py, fails
# the build if any gate returned `fail`. `warn` and `skipped` are reported
# but don't block.

# `set -e`: exit on any non-zero command (hardens against silent cd / tool
#   failures before we get to parse-gates.py).
# `-u`: treat unset variables as errors.
# `-o pipefail`: propagate non-zero exit codes through pipes (so we catch
#   web-gates.sh failing even though the pipeline continues to python).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

"$SCRIPT_DIR/web-gates.sh" --project-root "$REPO_ROOT" \
  | python3 "$SCRIPT_DIR/parse-gates.py"
