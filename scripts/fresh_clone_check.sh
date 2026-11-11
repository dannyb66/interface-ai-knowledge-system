#!/usr/bin/env bash
# Fresh-clone check: clone the repo, build a clean venv, run the public eval under the socket guard
# with scrubbed credentials, then assert the gates. Success prints one line; any failure prints one
# line to stderr and exits non-zero.
#   scripts/fresh_clone_check.sh [--python <path>] [--repo <path-or-url>] [--floor <score>] [--snapshots-zip <dir>]
# --floor defaults to public_final_score in the clone's results/baseline.json. Default --repo is this
# checkout, so only committed work is tested (that is the point). Runs on bash 3.2 (macOS) and newer.
# Website data is not published: supply its local archives with --snapshots-zip, or place them in
# this checkout's ignored snapshots_zip/ directory. Only ZIPs enter the temporary clone.
set -u

USAGE="usage: scripts/fresh_clone_check.sh [--python <path>] [--repo <path-or-url>] [--floor <score>] [--snapshots-zip <dir>]"
die() { printf 'fresh-clone: FAIL %s\n' "$*" >&2; exit 1; }
last_line() { tail -n 1 "$1" 2>/dev/null | tr -d '\r' | cut -c1-200; }

# An exported CDPATH makes cd print the directory it enters, which would corrupt the cd-and-pwd lines below.
unset CDPATH
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PY="$ROOT/.venv/bin/python"
PY=""
REPO="$ROOT"
FLOOR=""
SNAPSHOTS_ZIP="$ROOT/snapshots_zip"
while [ $# -gt 0 ]; do
  case "$1" in
    --python|--repo|--floor|--snapshots-zip)
      [ $# -ge 2 ] || die "$1 needs a value. $USAGE"
      case "$1" in --python) PY="$2" ;; --repo) REPO="$2" ;; --floor) FLOOR="$2" ;; --snapshots-zip) SNAPSHOTS_ZIP="$2" ;; esac
      shift 2 ;;
    -h|--help) echo "$USAGE"; exit 0 ;;
    *) die "unknown argument '$1'. $USAGE" ;;
  esac
done
if [ -n "$FLOOR" ]; then
  case "$FLOOR" in
    *[!0-9.]*|*.*.*|.) die "--floor '$FLOOR' is not a non-negative number" ;;
  esac
fi

# Validate before cloning or installing so a missing kit gets an actionable error.
[ -d "$SNAPSHOTS_ZIP" ] || die "snapshot archives are not included; use --snapshots-zip /path/to/participant-kit/snapshots_zip"
SNAPSHOTS_ZIP="$(cd "$SNAPSHOTS_ZIP" && pwd)" || die "cannot open snapshot archive directory"
ARCHIVES=("$SNAPSHOTS_ZIP"/*.zip)
[ -f "${ARCHIVES[0]}" ] || die "no ZIP archives in '$SNAPSHOTS_ZIP'; supply the participant kit's snapshots_zip directory"

# Resolve the interpreter before cloning: python3.11, else the dev venv, else python3.
if [ -z "$PY" ]; then
  if command -v python3.11 >/dev/null 2>&1; then PY=python3.11
  elif [ -x "$DEV_PY" ]; then PY="$DEV_PY"
  else PY=python3
  fi
fi
case "$PY" in
  */*) [ -x "$PY" ] && [ ! -d "$PY" ] || die "python '$PY' is not an executable file"
       PY="$(cd "$(dirname "$PY")" && pwd)/$(basename "$PY")" ;;
  *)   PY_FOUND="$(command -v "$PY")" || die "python '$PY' not found on PATH"
       PY="$PY_FOUND" ;;
esac

TMPBASE="${TMPDIR:-/tmp}"
TMP="$(mktemp -d "${TMPBASE%/}/fresh-clone.XXXXXX")" || die "cannot create a temp dir under $TMPBASE"
# shellcheck disable=SC2329  # invoked through the EXIT trap below
cleanup() { cd / && rm -rf "$TMP"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# Keys are scrubbed: nothing but PATH, HOME and two fake keys reaches the venv build or the eval run.
scrubbed() { env -i PATH="${PATH:-}" HOME="${HOME:-$TMP}" OPENAI_API_KEY=sk-fake ANTHROPIC_API_KEY=sk-fake "$@"; }

git clone --quiet -- "$REPO" "$TMP/clone" >"$TMP/git.log" 2>&1 \
  || die "git clone of '$REPO' failed: $(last_line "$TMP/git.log")"
cd "$TMP/clone" || die "cannot enter the clone"
mkdir -p snapshots_zip || die "cannot create the temporary snapshot archive directory"
cp "${ARCHIVES[@]}" snapshots_zip/ || die "cannot copy local snapshot archives into the temporary clone"

if [ -z "$FLOOR" ]; then
  [ -f results/baseline.json ] || die "no --floor given and results/baseline.json is not committed in the clone"
  FLOOR="$("$PY" -I -c 'import json,sys; print(float(json.load(open(sys.argv[1], encoding="utf-8"))["public_final_score"]))' \
    results/baseline.json 2>/dev/null)" || die "results/baseline.json has no numeric public_final_score"
fi

T_INSTALL=$SECONDS
scrubbed "$PY" -m venv .venv >"$TMP/venv.log" 2>&1 \
  || die "venv creation with $PY failed: $(last_line "$TMP/venv.log")"
scrubbed .venv/bin/pip install -q --disable-pip-version-check -r submission/requirements.txt >"$TMP/pip.log" 2>&1 \
  || die "pip install -r submission/requirements.txt failed: $(last_line "$TMP/pip.log")"
INSTALL_S=$((SECONDS - T_INSTALL))

RC=0
scrubbed .venv/bin/python scripts/_guarded_run_eval.py \
  --submission submission --eval eval/public_eval.jsonl --out results/fresh >"$TMP/run.log" 2>&1 || RC=$?
[ "$RC" -eq 0 ] || die "harness run exited $RC: $(last_line "$TMP/run.log")"
[ -f results/fresh/report.json ] || die "harness run wrote no results/fresh/report.json"

scrubbed .venv/bin/python scripts/check_prose_facts.py >"$TMP/prose.log" 2>&1 \
  || die "curated prose verification failed: $(last_line "$TMP/prose.log")"
scrubbed .venv/bin/python scripts/check_curated.py >"$TMP/curated.log" 2>&1 \
  || die "curated conflicts failed verification: $(last_line "$TMP/curated.log")"
.venv/bin/python -I - "$TMP/curated.log" <<'PY'
import json, pathlib, re, sys
with open("submission/data/conflicts_curated.json", encoding="utf-8") as fh:
    expected = len(json.load(fh)["conflicts"])
text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
summaries = re.findall(r"^curated: (\d+)/(\d+) verified$", text, flags=re.MULTILINE)
if summaries != [(str(expected), str(expected))]:
    sys.exit("fresh-clone: FAIL incomplete curated verification summary")
PY
[ "$?" -eq 0 ] || exit 1

.venv/bin/python -I - results/fresh/report.json "$FLOOR" "$INSTALL_S" <<'PY'
import json, sys
path, floor, install_s = sys.argv[1], float(sys.argv[2]), sys.argv[3]
try:
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    speed = report.get("speed")
except (OSError, ValueError, AttributeError) as exc:
    sys.exit("fresh-clone: FAIL %s unreadable: %s" % (path, exc))
errors = report.get("errors")
over_limit = report.get("ingest_over_limit")
p95 = speed.get("p95_s") if isinstance(speed, dict) else None
score = report.get("final_score")
failed = []
if errors != 0:
    failed.append("errors=%r (want 0)" % (errors,))
if over_limit is not False:
    failed.append("ingest_over_limit=%r (want False)" % (over_limit,))
if not (isinstance(p95, (int, float)) and p95 < 0.5):
    failed.append("speed.p95_s=%r (want < 0.5)" % (p95,))
if not (isinstance(score, (int, float)) and score >= floor):
    failed.append("final_score=%r (want >= %s)" % (score, floor))
if failed:
    sys.exit("fresh-clone: FAIL " + "; ".join(failed))
print("fresh-clone: OK score=%s p95=%ss install=%ss" % (score, p95, install_s))
PY
exit $?
