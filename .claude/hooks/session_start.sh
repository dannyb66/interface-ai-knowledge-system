#!/usr/bin/env bash
# SessionStart: one line with the active phase, the last public score and p95, and whether a
# handoff note exists.
#
# Contract: prints exactly one "kb-hook:" line on stdout; always exits 0. The EXIT trap enforces
# both, so every branch below only has to set MSG. No `set -e` on purpose. Does not read stdin.

MSG="hook did not finish"
EMITTED=""
emit_and_exit_zero() {
  if [ -z "$EMITTED" ]; then
    EMITTED=1
    printf 'kb-hook: %s\n' "${MSG%%$'\n'*}"
  fi
  exit 0
}
trap emit_and_exit_zero EXIT

ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)" || ROOT="$PWD"
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="python3"; fi
cd "$ROOT" 2>/dev/null || { MSG="phase=n/a public=n/a p95=n/a handoff=n/a"; exit 0; }

IFS= read -r -d '' PYPROG <<'PYEOF'
import glob, json, os, re, sys
os.chdir(sys.argv[1])


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


phase = "n/a"
try:
    with open(".planning/STATE.md", encoding="utf-8", errors="replace") as f:
        state = f.read()
    m = re.search(r"^[ \t>*-]*\**(?:current[ _])?phase\**[ \t]*:\**[ \t]*(.+?)[ \t]*$", state, re.I | re.M)
    if m:
        phase = " ".join(m.group(1).split())[:60] or "n/a"
except Exception:
    pass

pub = num("results/report.json", "final_score")
p95 = num("results/report.json", "speed", "p95_s")
notes = [".continue-here.md", ".planning/.continue-here.md"] + glob.glob(".planning/phases/*/.continue-here.md")
print("phase=%s public=%s p95=%s handoff=%s" % (
    phase,
    "n/a" if pub is None else "%.3f" % pub,
    "n/a" if p95 is None else "%.2fs" % p95,
    "yes" if any(os.path.isfile(n) for n in notes) else "no",
))
PYEOF

MSG="$("$PY" -c "$PYPROG" "$ROOT" 2>/dev/null)"
if [ -z "$MSG" ]; then MSG="phase=n/a public=n/a p95=n/a handoff=n/a"; fi
exit 0
