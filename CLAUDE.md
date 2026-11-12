# Knowledge system for a credit union website

Python system under `submission/` that answers member questions from five website snapshots without stale or wrong facts. Graded by `harness/run_eval.py`.

## Setup

Place the participant kit's five ZIPs in the ignored local `snapshots_zip/` directory first.

```
python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
```

## Verify (run all three before saying a change is done)

```
python -m pytest -q --ignore=tests/test_61_holdout.py --deselect=tests/test_62_proxy_prose.py::test_both_splits_have_all_prose_families_and_disjoint_claims --deselect=tests/test_96_eval_sets.py::test_locked_set_schema
python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
scripts/fresh_clone_check.sh --snapshots-zip snapshots_zip
```

## Scorer invariants (`harness/scoring.py`)

- Any `must_not_include` token in an answer zeroes that item, so numeric answers retain the resolved scope, never competing candidates. Reviewed prose answers preserve every required member of their complete claim groups.
- A refusal is `confident=False` plus a `REFUSAL_RE` phrase ("I can't confirm", "please contact") and no digit that is not already in the question.
- Numbers carry units (`4.10%`, `$1,000`, never a bare `4.10`); they are compared by value and unit.
- Tokens keep the site's surface form (`8 a.m.`, not `8:00 AM`).
- No network and no SDK import under `submission/`; stdlib only at runtime.

## Kit files are read-only

`harness/`, `eval/public_eval.jsonl`, `starter/`, `snapshots_zip/`, `snapshots/`. `.claude/settings.json` denies edits to them. Add new files beside them instead.

## Data

This public repository excludes the supplied website snapshots and credentials. Keep `snapshots/`,
`snapshots_zip/`, participant archives and API keys out of tracked files and public Git history.
The tiny artificial fixtures in `harness/selftest/snapshots/` are not supplied website crawls.
Derived runtime facts contain only the limited evidence needed for source verification.
Locked and holdout sets remain sealed; do not inspect them or use them as a tuning loop.
The pytest command above runs all nonsealed tests and explicitly excludes real sealed-content readers; retain synthetic privacy tests and report those exclusions. The fresh-clone gate verifies committed state and must be rerun after the candidate commit exists.

## Pointers

- `submission/NOTES.md`: the submission notes the kit asks for (keys, approach, what is current)
- `docs/SUBMISSION.md`: public repository and local kit setup for reviewers
- `docs/EVALUATION.md`: measured results and coverage limitations
