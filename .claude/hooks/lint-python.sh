#!/usr/bin/env bash
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PAYLOAD=$(cat)
FILE=$(printf '%s' "$PAYLOAD" | /usr/bin/python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
t = d.get("tool_input") or {}
r = d.get("tool_response") or {}
p = r.get("filePath") or t.get("file_path") or ""
print(p)
' 2>/dev/null)

case "$FILE" in
    "") exit 0 ;;
    *.py) ;;
    *) exit 0 ;;
esac

case "$FILE" in
    */tests/fixtures/*|tests/fixtures/*) exit 0 ;;
esac

case "$FILE" in
    "$ROOT"/src/*|"$ROOT"/tests/*) ;;
    src/*|tests/*) FILE="$ROOT/$FILE" ;;
    *) exit 0 ;;
esac

[ -f "$FILE" ] || exit 0
[ -x "$ROOT/.venv/bin/ruff" ] || exit 0

OUT=$(
    cd "$ROOT" || exit 0
    "$ROOT/.venv/bin/ruff" check --fix --quiet "$FILE" 2>&1
    "$ROOT/.venv/bin/ruff" format --quiet "$FILE" 2>&1
    if [ -x "$ROOT/.venv/bin/ty" ]; then
        "$ROOT/.venv/bin/ty" check --quiet "$FILE" 2>&1 | grep -v "^All checks passed" || true
    fi
)

if [ -n "$OUT" ]; then
    printf 'ruff/ty по %s:\n%s\n' "${FILE#"$ROOT"/}" "$OUT" >&2
    exit 2
fi
exit 0
