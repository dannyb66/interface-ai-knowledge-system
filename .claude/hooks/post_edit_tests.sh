#!/usr/bin/env bash
# PostToolUse (Edit|Write): after an edit under submission/, run the fast unit tests and report.
#
# Contract: reads Claude Code's JSON on stdin (tool_input.file_path); prints exactly one line on
# stdout containing "kb-hook:" (a plain line, or for a FAIL one PostToolUse JSON line carrying
# that text); always exits 0. The EXIT trap enforces both, so every branch below only has to set
# MSG. No `set -e` on purpose. Never fails on empty or non-JSON stdin.

MSG="hook did not finish"
EMITTED=""
emit_and_exit_zero() {
  if [ -z "$EMITTED" ]; then
    EMITTED=1
    LINE="kb-hook: ${MSG%%$'\n'*}"
    OUT=""
    # A failure goes out as PostToolUse JSON (additionalContext reaches the model; plain stdout
    # from a successful hook only reaches the debug log). python3 builds it so quoting is always
    # valid; if that fails the plain line below is printed instead. Every other message is plain.
    case "$MSG" in
      FAIL*)
        OUT="$(python3 -c 'import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": sys.argv[1]}}, separators=(",", ":")))' "$LINE" 2>/dev/null)"
        ;;
    esac
    printf '%s\n' "${OUT:-$LINE}"
  fi
  exit 0
}
trap emit_and_exit_zero EXIT

ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)" || ROOT="$PWD"
ROOT_P="$(cd "$ROOT" 2>/dev/null && pwd -P)" || ROOT_P="$ROOT"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="python3"; fi

# tool_input.file_path from stdin. Claude Code sends an absolute path; anything unexpected
# (empty stdin, not JSON, not an object, no string path) yields "".
FILE_PATH=""
if [ ! -t 0 ]; then
  FILE_PATH="$(python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input") if isinstance(d, dict) else None
    p = ti.get("file_path") if isinstance(ti, dict) else None
    sys.stdout.write(p if isinstance(p, str) else "")
except Exception:
    pass
' 2>/dev/null)"
fi

# Make the path repo-relative (the absolute form may use the logical or the physical root).
REL=$FILE_PATH
case "$FILE_PATH" in
  "$ROOT"/*)   REL=${FILE_PATH#"$ROOT"/} ;;
  "$ROOT_P"/*) REL=${FILE_PATH#"$ROOT_P"/} ;;
esac
REL=${REL#./}
case "$REL" in
  submission/*) ;;
  *) MSG="skipped (not submission/)"; exit 0 ;;
esac

# Only the fast tests that exist yet; the others arrive in later phases.
cd "$ROOT" 2>/dev/null || { MSG="FAIL repo root not found"; exit 0; }
FAST=()
for t in tests/test_00_normalize.py tests/test_30_compose.py; do
  if [ -f "$t" ]; then FAST+=("$t"); fi
done
if [ "${#FAST[@]}" -eq 0 ]; then
  MSG="tests ok (no fast tests yet)"
  exit 0
fi

IFS= read -r -d '' PYPROG <<'PYEOF'
import os, signal, subprocess, sys
root, files = sys.argv[1], sys.argv[2:]
cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"] + files
try:
    p = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, universal_newlines=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            p.kill()
        p.communicate()
        print("FAIL pytest timed out after 10s")
        sys.exit(0)
except Exception as exc:
    print("FAIL cannot run pytest (%s)" % type(exc).__name__)
    sys.exit(0)
if p.returncode == 0:
    print("tests ok")
    sys.exit(0)
lines = [l.strip() for l in out.splitlines() if l.strip()]
# Test ids come only from pytest's short summary; captured log and stdout lines print before it
# and can start with ERROR or FAILED too.
marks = [i for i, l in enumerate(lines) if "short test summary info" in l]
summary = lines[marks[-1] + 1:] if marks else []
ids = [l.split()[1] for l in summary if len(l.split()) > 1 and l.split()[0] in ("FAILED", "ERROR")]
print("FAIL " + (ids[0][:120] if ids else (lines[-1][:100] if lines else "pytest exit %d" % p.returncode)))
PYEOF

MSG="$("$PY" -c "$PYPROG" "$ROOT" "${FAST[@]}" 2>/dev/null)"
if [ -z "$MSG" ]; then MSG="FAIL could not run the fast tests"; fi
exit 0
