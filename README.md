# Snapshot-grounded knowledge system

Submission for interface.ai's Senior Software Engineer build assignment. The system answers questions from
five supplied credit-union website snapshots, selects current or historical facts, resolves conflicts, cites
sources and refuses unsupported claims. It uses only the Python standard library at runtime and requires no
API keys, model downloads or network access.

**Entry point:** [`submission/solution.py`](submission/solution.py), `build()`.
**Approach:** [`submission/NOTES.md`](submission/NOTES.md).
**Handoff:** [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

## Run the public evaluation

Use a clean **Python 3.11** environment with `python` available on your PATH. No API keys, external services,
model downloads or third-party runtime packages are needed.

1. Clone this repository:

   ```bash
   git clone https://github.com/dannyb66/interface-ai-knowledge-system.git
   cd interface-ai-knowledge-system
   ```

2. Obtain the participant kit from interface.ai. Place its five snapshot ZIP files in `snapshots_zip/` at the
   repository root. If they are already extracted, place the five crawl folders in `snapshots/` instead.
   The supplied data is excluded from Git because the assignment prohibits redistribution.

3. From the repository root, install the declared requirements and run the assignment command:

   ```bash
   python -m pip install -r submission/requirements.txt
   python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl
   ```

The harness automatically unpacks the ZIPs on the first run. `submission/requirements.txt` intentionally lists
no packages. A virtual environment is optional; create one using your platform's usual Python tools if needed.
The harness writes `results/report.json` and `results/per_question.jsonl`. Python 3.9 compatibility is also checked.

Organizers can instead copy the entire `submission/` folder into the top folder of their existing participant
kit and run the same command with their own `harness/`, `eval/` and snapshot data. In the PDF's command,
`<your folder>` means `submission` for this solution.

If the command reports `FileNotFoundError: ... 'snapshots'`, check that `snapshots_zip/` contains the five supplied
ZIPs or `snapshots/` contains their extracted crawl folders. A source-only clone does not include the dataset.

## Approach

Ingestion extracts typed facts from tables, rate lines, contact information, dated articles and fee schedules.
It verifies committed prose and conflict quotes against the supplied pages before admitting them. Facts retain
their product, attribute, tier qualifiers, dates and sources.

The parser turns each question into a canonical query. The resolver selects the applicable crawl, applies
publication/effective dates and authority, and keeps the requested product and tier. Templates render the
resolved facts and citations; numeric validation rejects unsupported values. Answer caching and explicit
ordering make replay deterministic. The runtime does not read evaluation labels.

## Results and limits

The verified Phase 3 runtime scores **0.9690 public**, **1.0000 dev** and **1.0000 generated proxy**, with zero
errors or stale-trap hits. All 238 curated prose source references and 22 curated conflicts verify. Description
or eligibility facts cover 41 of 44 eligible products; all 50 dollar-priced fee rows are extracted per crawl.
The public export passes **525 tests**, including three checks for missing or invalid local kit input.

Independent results reveal remaining limits: blind holdout QA is **0.9647**, with description **0.4095** and
eligibility **0.6667**; the broader locked set remains **0.0933**. These local results do not establish the
organizers' hidden score. Public item `dup-005` receives zero from the unchanged deterministic scorer because
its required-token list is empty; the optional semantic judge is not used in the no-key run.

The [measurement baseline](results/baseline.json) and [evaluation record](docs/EVALUATION.md) preserve the
measurement scope and limitations.

## Development checks

With the kit placed locally and the virtual environment active:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
scripts/eval.sh --public
scripts/eval.sh --dev
scripts/fresh_clone_check.sh --python "$(command -v python)" --snapshots-zip snapshots_zip
```

The fresh-clone check clones committed code into a temporary folder, copies only the local ZIP archives into
that folder, installs runtime requirements in a clean environment, runs the harness under a socket guard and
verifies every curated source. It does not publish data or test uncommitted changes. Missing kit data produces
an actionable error before cloning or installation.

Useful commands: `python scripts/ask.py "<question>" --explain`, `python scripts/bench.py --n 100`,
`python scripts/check_prose_facts.py` and `python scripts/check_curated.py`.

## Repository contents

- `submission/`: graded entry point, runtime and derived source-verified fact catalog.
- `harness/`, `starter/`, `eval/public_eval.jsonl`: unchanged organizer code and practice questions.
- `tests/`, `scripts/`, other `eval/` files: development checks and separate evaluation material.
- `harness/selftest/snapshots/`: small artificial fixtures, not the supplied website crawls.
- `.claude/`, `CLAUDE.md`: development workflow instructions exercised by the test suite.

Do not add supplied website snapshots, participant archives or API keys to this repository or its Git history.
Runtime facts contain only the limited derived evidence required for verification and answers.
