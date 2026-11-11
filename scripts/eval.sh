#!/usr/bin/env bash
# Run the harness on one eval set, then print what missed.
#   scripts/eval.sh [--public|--dev|--locked|--quick|--proxy|--holdout|--conflicts] [--out DIR]
#
#   --public    (default) eval/public_eval.jsonl, a full run                -> results/
#   --quick     the public set with --repeat-sample 0, the Stop hook's run  -> results/
#   --dev       eval/dev_extra.jsonl, never mixed into a public run         -> results/dev/
#   --locked    eval/locked/locked_set.jsonl: prints ONE aggregate score line and nothing else; its
#               per-item rows go to a temp directory that is removed again, unless --out names one
#   --proxy     eval/proxy/proxy.jsonl (scripts/build_proxy_set.py)         -> results/proxy/
#   --holdout   eval/proxy/holdout.jsonl: aggregate score and family summaries only (scored once per phase)
#   --conflicts the public set with --conflicts-gold eval/conflicts_gold_dev.json -> results/conflicts/:
#               ONE line, the conflicts block (score_conflicts) and final_score; harness log in harness.log
#   --out DIR   where the harness writes per_question.jsonl and report.json (default as above)
#
# Every mode runs harness/run_eval.py through scripts/_guarded_run_eval.py, the socket guard. --public,
# --quick, --dev and --proxy print the harness summary (it carries the per-category scores), then a table of
# the items that scored below 1.0: id, category, weight, missed, trap_hits, refusal? and score, trap hits
# first, then weight. --public and --quick touch results/.last_eval, the stamp the Stop hook compares with
# submission/, but only when the report landed in results/ (no --out, or --out naming that directory): the
# stamp says "the public report there is fresh". Every other mode and a --out elsewhere leave it alone. Works
# from any directory, prefers .venv/bin/python when the repo has one, and runs on bash 3.2 (macOS) and newer.
# Proxy and holdout also print aggregate family scores through proxy_report.py. Enforce the proxy phase gate
# with: python scripts/proxy_report.py --results DIR --gate (seeds and generated items are reported separately).
set -u

usage() { echo "usage: scripts/eval.sh [--public|--dev|--locked|--quick|--proxy|--holdout|--conflicts] [--out DIR]"; }
die_usage() { { echo "eval.sh: $1"; usage; } >&2; exit 2; }

# An exported CDPATH makes cd print the directory it enters, which would corrupt the cd-and-pwd line below.
unset CDPATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)" || { echo "eval.sh: cannot find the repo root" >&2; exit 2; }
if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY=python3; fi

MODE=""
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --public|--dev|--locked|--quick|--proxy|--holdout|--conflicts)
      NEW="${1#--}"
      if [ -n "$MODE" ] && [ "$MODE" != "$NEW" ]; then
        die_usage "pick one of --public, --dev, --locked, --quick, --proxy, --holdout, --conflicts (got --$MODE and --$NEW)"
      fi
      MODE="$NEW" ;;
    --out)
      [ $# -ge 2 ] || die_usage "--out needs a directory"
      OUT="$2"
      shift ;;
    --out=*) OUT="${1#--out=}" ;;
    -h|--help) usage; exit 0 ;;
    *) die_usage "unknown argument: $1" ;;
  esac
  shift
done
[ -n "$MODE" ] || MODE=public

case "$MODE" in
  public|quick) SET="$ROOT/eval/public_eval.jsonl"; DEFAULT_OUT="$ROOT/results" ;;
  dev)          SET="$ROOT/eval/dev_extra.jsonl"; DEFAULT_OUT="$ROOT/results/dev" ;;
  locked)       SET="$ROOT/eval/locked/locked_set.jsonl"; DEFAULT_OUT="" ;;
  proxy)        SET="$ROOT/eval/proxy/proxy.jsonl"; DEFAULT_OUT="$ROOT/results/proxy" ;;
  holdout)      SET="$ROOT/eval/proxy/holdout.jsonl"; DEFAULT_OUT="" ;;
  conflicts)    SET="$ROOT/eval/public_eval.jsonl"; DEFAULT_OUT="$ROOT/results/conflicts" ;;
esac
# The one-line modes show no harness output; --locked and --holdout also keep no per-item rows (a temp --out).
ONE_LINE=""; HIDDEN=""
case "$MODE" in locked|holdout) ONE_LINE=1; HIDDEN=1 ;; conflicts) ONE_LINE=1 ;; esac

SCRATCH=""
# shellcheck disable=SC2329  # invoked through the EXIT trap below
cleanup() { [ -z "$SCRATCH" ] || rm -rf "$SCRATCH"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -n "$HIDDEN" ]; then
  TMP_BASE="${TMPDIR:-/tmp}"
  SCRATCH="$(mktemp -d "${TMP_BASE%/}/kb-$MODE.XXXXXX")" || { echo "eval.sh: cannot create a temp directory" >&2; exit 2; }
  [ -n "$OUT" ] || OUT="$SCRATCH/out"
  LOG="$SCRATCH/harness.log"
else
  [ -n "$OUT" ] || OUT="$DEFAULT_OUT"
  LOG="$OUT/harness.log"
fi

# Absolute paths throughout and no cd, so a relative --out stays relative to the caller's directory.
ARGS=(--submission "$ROOT/submission" --snapshots "$ROOT/snapshots" --eval "$SET" --out "$OUT")
if [ "$MODE" = quick ]; then ARGS+=(--repeat-sample 0); fi
if [ "$MODE" = conflicts ]; then ARGS+=(--conflicts-gold "$ROOT/eval/conflicts_gold_dev.json"); fi

if [ -n "$ONE_LINE" ]; then
  [ -n "$HIDDEN" ] || mkdir -p "$OUT" || { echo "eval.sh: cannot create $OUT" >&2; exit 2; }
  "$PY" "$ROOT/scripts/_guarded_run_eval.py" "${ARGS[@]}" >"$LOG" 2>&1  # nothing of it is shown
else
  "$PY" "$ROOT/scripts/_guarded_run_eval.py" "${ARGS[@]}"
fi
RC=$?
if [ "$RC" -ne 0 ]; then
  if [ -n "$HIDDEN" ]; then echo "eval.sh: the $MODE run failed (exit $RC)" >&2
  elif [ -n "$ONE_LINE" ]; then echo "eval.sh: the $MODE run failed (exit $RC); see $LOG" >&2
  else echo "eval.sh: the harness exited $RC" >&2; fi
  exit "$RC"
fi

# The stamp says "the public report in results/ is fresh", so only a public-set run that wrote there touches it.
same_dir() { [ -d "$1" ] && [ -d "$2" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]; }
if { [ "$MODE" = public ] || [ "$MODE" = quick ]; } && same_dir "$OUT" "$ROOT/results"; then
  touch "$ROOT/results/.last_eval"
fi

print_one_line() {
  "$PY" - "$OUT/report.json" "$MODE" <<'PYEOF'
import json, sys

mode = sys.argv[2]
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        report = json.load(fh)
    if mode == "conflicts":
        c = report["conflicts"]
        ra = c["resolution_accuracy"]
        print("conflicts gold=%d submitted=%d matched=%d precision=%.4f recall=%.4f f1=%.4f resolution_accuracy=%s "
              "final_score=%.4f" % (c["gold"], c["submitted"], c["matched"], c["precision"], c["recall"], c["f1"],
                                    "n/a" if ra is None else "%.4f" % ra, report["final_score"]))
    else:
        print("%s final_score=%.4f qa_score=%.4f questions=%d errors=%d" % (
            mode, report["final_score"], report["qa_score"], report["questions"], report["errors"]))
except Exception:
    print("eval.sh: the %s run left no readable aggregate score" % mode, file=sys.stderr)
    sys.exit(1)
PYEOF
}

print_miss_table() {
  "$PY" - "$OUT" "$ROOT" <<'PYEOF'
import json, os, sys

out, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "harness"))
try:
    from scoring import REFUSAL_RE
except Exception:  # without the scorer's pattern only the confident flag counts as a refusal
    REFUSAL_RE = None

with open(os.path.join(out, "per_question.jsonl"), encoding="utf-8") as fh:
    rows = [json.loads(line) for line in fh if line.strip()]


def refused(row):
    answer = row.get("answer") or {}
    if answer.get("confident") is False:
        return True
    return bool(REFUSAL_RE and REFUSAL_RE.search(answer.get("text") or ""))


def cell(items, width):
    text = "; ".join(str(i) for i in items) if items else "-"
    return text if len(text) <= width else text[: width - 3] + "..."


misses = sorted(
    (r for r in rows if r.get("score", 0) < 1),
    key=lambda r: (0 if r.get("trap_hits") else 1, -float(r.get("weight", 1)), str(r.get("id"))),
)
header = ("id", "category", "weight", "missed", "trap_hits", "refusal?", "score")
body = [
    (str(r.get("id")), str(r.get("category")), "%g" % float(r.get("weight", 1)), cell(r.get("missed"), 48),
     cell(r.get("trap_hits"), 24), "yes" if refused(r) else "no", "%.2f" % r.get("score", 0))
    for r in misses
]
widths = [max([len(header[i])] + [len(b[i]) for b in body]) for i in range(len(header))]
print()
print("misses: %d of %d items scored below 1.0 (trap hits first, then weight)" % (len(misses), len(rows)))
print("  ".join(h.ljust(w) for h, w in zip(header, widths)).rstrip())
for b in body:
    print("  ".join(c.ljust(w) for c, w in zip(b, widths)).rstrip())
if not body:
    print("(none)")
print("files: %s, %s" % (os.path.join(out, "report.json"), os.path.join(out, "per_question.jsonl")))
PYEOF
}

if [ -n "$ONE_LINE" ]; then print_one_line; else print_miss_table; fi
RC=$?
if [ "$RC" -eq 0 ] && { [ "$MODE" = proxy ] || [ "$MODE" = holdout ]; }; then
  "$PY" "$ROOT/scripts/proxy_report.py" --set "$SET" --results "$OUT"
  RC=$?
fi
exit "$RC"
