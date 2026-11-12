# Submission and reproduction

The recruiter email requests a **public GitHub repository**, excluding the supplied website snapshots and any
API keys. Send the repository URL and full grading commit to **assignments@interface.ai**. There is **no fixed
deadline**; submit when the work represents your best effort. Public read access replaces private invitations.

**Current status:** Phase 4 is a **reviewed, unpromoted candidate**. Ordinary regression and independent
development review are complete; the final blind comparison is unrun. The immutable `submission-v1`
tag at `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38` remains the grading fallback. This handoff draft does not
select a new grading commit or confirm that an email has been sent. Measured candidate scores and limits
are in the [evaluation record](EVALUATION.md); they do not constitute blind release approval.

| Field | Value |
| --- | --- |
| Repository | <https://github.com/dannyb66/interface-ai-knowledge-system> |
| Graded folder | `submission` |
| Entry point | [`submission/solution.py`](../submission/solution.py), `build()` |
| Runtime dependencies | [`submission/requirements.txt`](../submission/requirements.txt), standard library only |
| API keys | None |
| Approach and current-value rules | [`submission/NOTES.md`](../submission/NOTES.md) |
| Grading commit | Use the full commit supplied in the submission email; verify with `git rev-parse HEAD`. |
| Delivery | Email the public URL and full commit to `assignments@interface.ai`. |

## Clean Python 3.11 run

Export `GRADING_SHA` with the full 40-character commit supplied in the submission email. The commands below
require that value, clone the public GitHub repository, detach at that exact commit and assert the resulting
HEAD. A default-branch checkout is not sufficient:

```bash
set -eu
: "${GRADING_SHA:?Export GRADING_SHA with the full grading commit}"
test "${#GRADING_SHA}" -eq 40
git clone https://github.com/dannyb66/interface-ai-knowledge-system.git
cd interface-ai-knowledge-system
git fetch origin "$GRADING_SHA"
git checkout --detach "$GRADING_SHA"
test "$(git rev-parse HEAD)" = "$GRADING_SHA"
```

Use an installed Python 3.11 interpreter to create a clean environment (`python3.11` below, or its full path):

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version'
```

Obtain the participant kit from interface.ai. Place its five ZIPs in `snapshots_zip/` at the repository root,
or place its five extracted crawl folders in `snapshots/`. The website data is supplied separately and is not
part of this public repository. From the repository root, run:

```bash
python -m pip install -r submission/requirements.txt
python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
```

No custom setup script, machine-specific path or bundled virtual environment is required. Organizers may
instead copy the entire `submission/` folder into their existing participant kit and run the same command
with their own scorer and data. The PDF's `<your folder>` placeholder is `submission` for this repository.

The unchanged harness unpacks the ZIPs into `snapshots/`, ingests all five crawls oldest first and evaluates
`build()`, `answer()` and `conflicts()`. Reports go under ignored `results/`. No generated local index, API key
or external service is required. Do not enable `--judge` when reproducing the recorded no-key score.

For local committed-code checks, the existing helper accepts an external kit directory without copying data
into the working checkout:

```bash
scripts/fresh_clone_check.sh --python python3.11 --snapshots-zip /path/to/participant-kit/snapshots_zip
```

It copies only local ZIP archives into a temporary clone and removes that clone afterward. By default it clones
the local repository; `--repo` can select another repository but does not pin a commit. It has no `--ref` or
expected-SHA option. Its p95 limit is 500 ms, so it does not enforce the stricter Phase 4 limit of 50 ms.

## Exact-SHA remote release verification

After freezing and pushing the candidate, run the GitHub clone, detached checkout and HEAD assertion above
in a new directory, then create the clean Python 3.11 environment and supply the external kit locally. In that
same asserted checkout, install the runtime requirements and run:

```bash
python -m pip install -r submission/requirements.txt
python scripts/_guarded_run_eval.py --submission submission \
  --eval eval/public_eval.jsonl --out results/release-public
python scripts/check_prose_facts.py
python scripts/check_curated.py
test "$(git rev-parse HEAD)" = "$GRADING_SHA"
```

Record the full SHA, interpreter, commands and aggregate outputs. Every curated source must verify against
the local kit. A successful local clone or a GitHub clone of a different commit does not pass this gate.
Python 3.9 compatibility, final regression/proxy/conflict preservation, p95 below 50 ms and independent
semantic/blind acceptance remain separate requirements. Recheck the exact final grading SHA if any release
files change after verification. The [implementation review](phase4/IMPLEMENTATION_REVIEW.md) tracks those gates.

## Checklist

- Publish the solution code and full grading commit in this public repository.
- Keep actual website snapshots, participant archives and API keys out of tracked files **and complete public
  Git history**. `.gitignore` protects the usual local data and credential paths.
- Keep `solution.py` outside `starter/`, declare runtime requirements and include concise approach/key notes.
- Finish independent semantic and regression gates before promoting Phase 4; otherwise retain `submission-v1`.
- Verify the exact frozen GitHub commit from a clean Python 3.11 clone with the participant kit supplied locally.
- Keep `submission-v1` immutable; create a new grading tag only after the candidate passes all gates.
- Email the public URL and exact commit to `assignments@interface.ai`; a draft is not a sent submission.

No hidden evaluation score is claimed. The [evaluation record](EVALUATION.md) discloses independent coverage
weaknesses alongside the public score.
