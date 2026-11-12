# Snapshot-grounded knowledge system

Submission for interface.ai's Senior Software Engineer build assignment. The system answers questions from
five supplied credit-union website snapshots, selects current or historical facts, resolves conflicts, cites
sources and refuses unsupported claims. It uses only the Python standard library at runtime and requires no
API keys, model downloads or network access.

**Entry point:** [`submission/solution.py`](submission/solution.py), `build()`.
**Approach:** [`submission/NOTES.md`](submission/NOTES.md).
**Handoff:** [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

**Release status:** Phase 4 is an **unpromoted candidate under verification**. The immutable
`submission-v1` tag at `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38` remains the grading fallback.
The final corrected candidate passed **1,009 nonsealed tests**, with **0.9690 public**, **1.0000 original dev**
and **0.9976 proxy**. Broader independent development semantic success is **0.155556** (16/98 paired scenarios),
with zero reviewed unsupported, stale, citation or temporal failures. Generalization remains limited, and the
new blind comparison is **unrun**. The [implementation review](docs/phase4/IMPLEMENTATION_REVIEW.md) and
[evaluation record](docs/EVALUATION.md) distinguish completed verification from pending release gates.

## Run the public evaluation

Use a clean **Python 3.11** environment with `python` available on your PATH. No API keys, external services,
model downloads or third-party runtime packages are needed.

1. Export `GRADING_SHA` with the full 40-character commit supplied with the submission. Clone GitHub and
   check out that exact commit; the default branch is not a substitute:

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
The harness writes `results/report.json` and `results/per_question.jsonl`. The corrected candidate also passed actual Python 3.9 compatibility checks and exact answer parity on all
60 public/original-dev questions.

Organizers can instead copy the entire `submission/` folder into the top folder of their existing participant
kit and run the same command with their own `harness/`, `eval/` and snapshot data. In the PDF's command,
`<your folder>` means `submission` for this solution.

If the command reports `FileNotFoundError: ... 'snapshots'`, check that `snapshots_zip/` contains the five supplied
ZIPs or `snapshots/` contains their extracted crawl folders. A source-only clone does not include the dataset.

## Approach

Ingestion extracts typed facts from tables, rate lines, contact information, dated articles and fee schedules.
It verifies curated prose and conflict quotes against the supplied pages before admitting them. Source identity
retains the actual crawl, raw URL and content hash, including distinct captures at a shared canonical URL.
Facts retain their product, attribute, conditions, tier qualifiers and dates.

The parser turns each question into a canonical query. The resolver selects the applicable crawl, applies
publication/effective dates and authority, and keeps the requested product and tier. Templates render the
resolved facts and citations; numeric validation rejects unsupported values. Answer caching and explicit
ordering make replay deterministic. Complete eligibility, procedure and declared description groups must retain
every required claim through source verification and selection. Conditional fees keep their customer/service
scope, dated prose retains attribution, and rates marked “as low as” keep that bound. Conflict notes require the
applicable product, tier and date, with supporting citations.

Compound prose is limited to eligibility plus service information for one recognized entity; both parts must
be supported. Both optional routing flags remain **off**. The earlier six-arm ablation produced no answer
changes. Later unknown-topic routing added one unadopted answer; an isolated source-context variant produced
no additional recovery attributable to its new mechanism and was rejected. The
[implementation review](docs/phase4/IMPLEMENTATION_REVIEW.md) records these decisions. No model-based prose builder was activated.
The runtime does not read evaluation labels.

## Results and limits

The historical Phase 3 fallback scored **0.9690 public**, **1.0000 original dev** and **1.0000 generated proxy**,
with zero errors or stale-trap hits. Its 238 curated prose source references and 22 curated conflicts verified;
description or eligibility facts covered 41 of 44 eligible products. Its public export passed **525 tests**.
These measurements belong to the fallback; the corrected Phase 4 measurements are recorded above.

Historical independent results revealed limits: blind holdout QA was **0.9647**, with description **0.4095** and
eligibility **0.6667**; the broader locked set scored **0.0933**. These local results do not establish the
organizers' hidden score. Public item `dup-005` receives zero from the unchanged deterministic scorer because
its required-token list is empty; the optional semantic judge is not used in the no-key run.

The reviewed Phase 4 source catalog currently has **397 entries**, with **1,794 entry/page/crawl pairs** and
**1,602 exact source pins**. Its reviewed-requirements matrix has **654 complete rows out of 680**. The 26
documented historical gaps comprise 24 fee scopes and two older advisor scopes. These are source-coverage
counts, not answer scores. Final runtime/data hashes are bound in the evaluation record. See
[source coverage](docs/phase4/SOURCE_COVERAGE.md) for exclusions and scope.

Ordinary regression and independent development review are complete. The final blind comparison and release
promotion remain pending; exact-SHA remote-clone verification is recorded in the submission handoff.
The [historical baseline](results/baseline.json) and [evaluation record](docs/EVALUATION.md) preserve the
measurement scope and remaining release requirements.

## Development checks

With the kit placed locally and the virtual environment active:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q --ignore=tests/test_61_holdout.py \
  --deselect=tests/test_62_proxy_prose.py::test_both_splits_have_all_prose_families_and_disjoint_claims \
  --deselect=tests/test_96_eval_sets.py::test_locked_set_schema
scripts/eval.sh --public
scripts/eval.sh --dev
scripts/fresh_clone_check.sh --python "$(command -v python)" --snapshots-zip snapshots_zip
```

The fresh-clone check clones committed code into a temporary folder, copies only the local ZIP archives into
that folder, installs runtime requirements in a clean environment, runs the harness under a socket guard and
verifies every curated source. It does not publish data or test uncommitted changes. Missing kit data produces
an actionable error before cloning or installation. It has no `--ref` or expected-SHA option, and its latency
check is looser than the Phase 4 gate. Follow the [exact-SHA remote verification](docs/SUBMISSION.md) for release.

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
