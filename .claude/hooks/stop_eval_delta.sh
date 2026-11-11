#!/usr/bin/env bash
# Stop: when submission/ changed since the last eval, run scripts/eval.sh --quick and print the
# public score and its delta against results/baseline.json.
#
# Contract: prints exactly one line on stdout containing "kb-hook:" (a plain line, or for the
# score line one {"systemMessage": ...} JSON line carrying that text); always exits 0. The EXIT
# trap enforces both, so every branch below only has to set MSG. No `set -e` on purpose. Does not
# read stdin. results/.last_eval is touched here only after an eval run that exited 0.

MSG="hook did not finish"
EMITTED=""
emit_and_exit_zero() {
  if [ -z "$EMITTED" ]; then
    EMITTED=1
    LINE="kb-hook: ${MSG%%$'\n'*}"
    OUT=""
    # The score line goes out as {"systemMessage": ...} so Claude Code shows it to the user (plain
    # stdout from a successful Stop hook only reaches the debug log). python3 builds the JSON so
    # quoting is always valid; if that fails the plain line below is printed instead. Every other
    # message is plain.
    case "$MSG" in
      "public "*)
        OUT="$(python3 -c 'import json, sys
print(json.dumps({"systemMessage": sys.argv[1]}, separators=(",", ":")))' "$LINE" 2>/dev/null)"
        ;;
    esac
    printf '%s\n' "${OUT:-$LINE}"
  fi
  exit 0
}
trap emit_and_exit_zero EXIT

ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)" || ROOT="$PWD"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="python3"; fi
cd "$ROOT" 2>/dev/null || { MSG="eval skipped (repo root not found)"; exit 0; }

STAMP="results/.last_eval"
if [ ! -f scripts/eval.sh ]; then
  MSG="eval script not available yet"
  exit 0
fi
if [ -f "$STAMP" ]; then
  CHANGED="$(find submission -type f -newer "$STAMP" ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.DS_Store' 2>/dev/null | head -n 1)"
  if [ -z "$CHANGED" ]; then
    MSG="no submission changes since last eval"
    exit 0
  fi
fi

IFS= read -r -d '' PYPROG <<'PYEOF'
import json, os, signal, subprocess, sys, time
os.chdir(sys.argv[1])
TIMEOUT = 45  # seconds; Claude Code's own default hook limit is 60


def num(path, *keys):
    """A float read from a JSON file, or None when the file, a key or the number is missing."""
    try:
        with open(path) as f:
            v = json.load(f)
        for k in keys:
            v = v[k]
        return float(v)
    except Exception:
        return None


start = time.time()
try:
    p = subprocess.Popen(["bash", "scripts/eval.sh", "--quick"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        rc = p.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            p.kill()
        p.wait()
        print("eval timed out after %ds" % TIMEOUT)
        sys.exit(0)
except Exception as exc:
    print("eval could not run (%s)" % type(exc).__name__)
    sys.exit(0)
if rc != 0:
    print("eval failed (exit %d)" % rc)
    sys.exit(0)

try:
    os.makedirs("results", exist_ok=True)
    with open("results/.last_eval", "a"):
        pass
    os.utime("results/.last_eval", None)
except Exception:
    pass

report = "results/report.json"
fresh = os.path.exists(report) and os.path.getmtime(report) >= start - 2  # never show an old report
score = num(report, "final_score") if fresh else None
base = num("results/baseline.json", "public_final_score")
s = "n/a" if score is None else "%.3f" % score
b = "n/a" if base is None else "%.3f" % base
d = "n/a" if score is None or base is None else "%+.3f" % (round(score - base, 3) + 0.0)
print("public %s (baseline %s, %s)" % (s, b, d))
PYEOF

MSG="$("$PY" -c "$PYPROG" "$ROOT" 2>/dev/null)"
if [ -z "$MSG" ]; then MSG="eval could not run"; fi
exit 0
