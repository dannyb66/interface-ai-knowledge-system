# Submission and reproduction

The recruiter email requests a **public GitHub repository**, excluding the supplied website snapshots and any
API keys. Send the repository URL and full grading commit to **assignments@interface.ai**. There is **no fixed
deadline**; submit when the work represents your best effort. Public read access replaces private invitations.

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

Use a clean Python 3.11 environment where `python` selects that interpreter. Clone this public repository and
check out the full commit in the submission email:

```bash
git clone https://github.com/dannyb66/interface-ai-knowledge-system.git
cd interface-ai-knowledge-system
# git checkout --detach <full-commit-from-the-submission-email>
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

The committed-code verification command can instead take an external kit directory without copying data into
the working checkout:

```bash
scripts/fresh_clone_check.sh --python python3.11 --snapshots-zip /path/to/participant-kit/snapshots_zip
```

It copies only local ZIP archives into a temporary clone and removes that clone afterward. Every source quote
must verify against the supplied kit. The runtime also supports Python 3.9.

## Checklist

- Publish the solution code and full grading commit in this public repository.
- Keep actual website snapshots, participant archives and API keys out of tracked files **and complete public
  Git history**. `.gitignore` protects the usual local data and credential paths.
- Keep `solution.py` outside `starter/`, declare runtime requirements and include concise approach/key notes.
- Verify the public evaluation from a clean clone with the participant kit supplied locally.
- Email the public URL and exact commit to `assignments@interface.ai`; a draft is not a sent submission.

No hidden evaluation score is claimed. The [evaluation record](EVALUATION.md) discloses independent coverage
weaknesses alongside the public score.
