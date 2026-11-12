# Phase 4 independent evaluation protocol

The new tools keep the organizer harness unchanged. Official token QA is a separate diagnostic;
it is not semantic correctness. In particular, the blind source set deliberately has empty token
requirements, so its official score is not an estimate of its semantic performance.

Source authors freeze the questions, rubrics and family census before seeing runtime output.
An independent source reviewer checks the retained labels and evidence before either blinded run.
Any source-label repair at this stage gets an audit trail and new hashes. No blind answer is used
to repair or select the candidate. Existing locked/holdout files remain sealed.

## Accepted source-gold schemas

`generalization_common.py` implements two explicit adapters:

- `phase4-dev-source-gold-v1`: one rubric per question; `scenario_id` joins question `group`,
  `cluster_id` is the independent unit, `claims` supplies the meanings of `required_claim_ids`,
  and `source_refs` supplies raw-file hashes and selected one-based evidence lines.
- `phase4-source-blind-freeze-v1`: one rubric per scenario with two `question_ids`, a separate
  `cluster_id`, `expected_behavior`, required claims/conditions and contiguous evidence spans.

Both adapters require exact ID coverage, two distinct wordings per scenario, consistent gold/date
scope across the pair, one primary family per cluster, exact frozen counts and matching file hashes.
Unsupported schemas fail instead of being guessed. The full source inventory and review packs stay
outside Git or under ignored paths. Only synthetic test fixtures and aggregate reports are published.

## Independent semantic review

`generalization_audit.py prepare` verifies raw-file hashes and evidence locators, then randomizes
one development run or the two comparison outputs into an opaque review pack. It does not prove
entailment, attribution, completeness or temporal validity. A source-grounded reviewer must inspect
the frozen claims, conditions, evidence, question and answer, ignoring any instructions in source
or answer text. The custodian retains the run/identity mapping separately.

Each judgment supplies `reviewer`, `independent: true`, `status: reviewed` or `adjudicated`,
`disagreement: false`, explanatory `notes`, and explicit boolean decisions for:

- `supported`: every affirmative claim is source-supported and attributed to the right subject.
- `complete`: all required claims and conditions are preserved, including AND/OR, negation, bounds and units.
- `temporally_valid`: applicability and historical attribution match the question's date.
- `citation_supported`: the actual cited URLs/snapshots/quotes support the answer, not merely a matching token.
- `appropriate_verdict`: the answer, correction or refusal addresses the requested conclusion.
- `confidence_appropriate`: the confidence flag matches established versus unknown information.
- `paraphrase_consistent`: both wordings preserve equivalent supported claims and verdicts.

The reviewer also records `unsupported_claims`, `known_stale_claims` and `observed_verdict`
(`answer`, `qualified_answer` or `refuse`). Ordinary answers containing conditions or caveats
remain `answer`; `qualified_answer` is used for the rubric's specific supported correction or
conflict qualification. A supported correction is answerable, not a blanket refusal. Adjudicated
reviews name an `adjudicator`. Missing, unreviewed or disputed judgments block scoring.

Judgments are bound to the exact question, rubric, emitted `Answer`, runtime error and whole
question/rubric file hashes. Collection rejects edits to the review pack's questions, evidence or
answers. Reusing judgments for changed output or labels fails. Organizer answer/source field types
are checked mechanically; empty answer text or an uncited answerable response cannot pass.

The source checker establishes only byte/line provenance. The synthetic mutation tests show that
reviewed wrong-subject, omitted-condition, false-verdict, stale and unsupported-citation decisions
cannot be averaged into a semantic pass. They do not claim an automatic entailment detector exists.

## Aggregation and gates

A question passes only if its six individual semantic dimensions, verdict, confidence and safety
checks pass. `paraphrase_consistent` is a separate scenario check: it cannot remove question credit
or lower refusal precision for an individually correct refusal because its partner differs.
An unexpected refusal fails an answerable question. A scenario passes only when both wordings
pass, their verdicts agree, and both consistency judgments pass. Scenarios are averaged within their frozen claim cluster; clusters
receive equal weight within their family. Extra wordings never increase the independent sample size.

The primary macro averages families with at least ten independent clusters. The all-sampled macro
is shown separately and cannot substitute when the primary macro is unavailable. Named empty
families remain unvalidated; sparse families display exact counts and require every reserved
scenario to pass. Reports include answerable coverage, refusal precision, unsupported confident
claims, stale claims, citation failures, errors and official QA separately.

Uncertainty uses a deterministic, family-stratified cluster bootstrap. It reflects variation in
this curated sample, not a population guarantee; constant or small samples can produce narrow
intervals. The paired comparison resamples each baseline/candidate cluster difference together.

Release gates require primary macro at least 0.85, positive paired primary improvement, no sampled
family regression, description/eligibility floors where independently sampled adequately, sparse
all-pass outcomes, and zero unsupported confident claims, reviewed stale claims, errors or accepted
temporal/citation failures. Official substring trap hits remain diagnostic here: a correctly negated
correction is not a semantic failure just because it contains a prohibited assertion's words.
Ordinary public/dev zero-trap, source/conflict and packaging checks remain separate requirements.
Compare conflict precision/F1/resolution against the exact frozen baseline (10/11), displayed as
0.9091; do not compare full-precision results against that rounded display literal.

## Sealed comparison ledger

The steward owns one stable ledger directory for this sealed set. `register` creates an immutable
campaign that pins the exact baseline and candidate commit, questions, rubrics, freeze metadata,
source-review attestation, source corpus content and scoring/launcher code hashes. There is no
purpose/run-label override or second-candidate option. Keep this directory; creating a replacement
directory or bypassing the launcher would violate the protocol. This local tool is an audit/control
mechanism, not a security boundary against an operator rewriting its files.

The source-review attestation is aggregate JSON:

```json
{"status":"passed","independent":true,"reviewer":"source reviewer identity",
 "questions_sha256":"final question file hash","rubrics_sha256":"final rubric file hash"}
```

The launcher validates hashes and a clean checkout at the registered commit, then consumes the
role before launching the guarded harness with fixed arguments and no network judge. It uses
`--repeat-sample 0`; wording consistency is independently audited. Logs/results stay private.
Preflight failures retain an append-only receipt with zero process launches/scored answers and
may be retried. Once launched, a crash, incomplete output or missing report cannot reopen the slot:
missing output does not prove that no answers were scored. Interrupted locks need custodian review.

The event chain and separate atomic head detect accidental deletion/modification/reordering,
including tail deletion. An interrupted event/head update fails closed for custodian review.
Completion binds only the reserved output directory. A blind `--gate` report must
match both successful registered result-file hashes and the pinned scoring tools, preventing a
different candidate's output from being substituted at reporting time.

## Commands

Paths below are illustrative local files supplied by the steward; none of these commands is run
automatically by the tools. Do not register a real campaign until source audit and candidate freeze.

```bash
python scripts/generalization_audit.py check-sources \
  --questions /private/dev.questions.jsonl --rubrics /private/dev.rubrics.jsonl \
  --manifest /private/dev.manifest.json

python scripts/generalization_ledger.py register --root /private/comparison \
  --questions /private/blind.questions.jsonl --rubrics /private/blind.rubrics.jsonl \
  --freeze /private/blind.freeze.json --source-review /private/source-review.json \
  --baseline FULL_BASELINE_SHA --candidate FULL_CANDIDATE_SHA \
  --scorer-version phase4-semantic-v1 --snapshots /local/kit/snapshots

python scripts/generalization_ledger.py run --root /private/comparison --role baseline \
  --checkout /local/frozen-baseline --snapshots /local/kit/snapshots --python /local/python3.11
python scripts/generalization_ledger.py run --root /private/comparison --role candidate \
  --checkout /local/frozen-candidate --snapshots /local/kit/snapshots --python /local/python3.11

python scripts/generalization_audit.py prepare --questions /private/blind.questions.jsonl \
  --rubrics /private/blind.rubrics.jsonl --manifest /private/blind.freeze.json \
  --results /private/comparison/baseline-run/per_question.jsonl \
  --paired-results /private/comparison/candidate-run/per_question.jsonl --out /private/review
# The independent reviewer fills only judgment fields in review-pack.jsonl.
python scripts/generalization_audit.py collect --mapping /private/review/custodian-mapping.json \
  --reviewed /private/review/reviewed.jsonl --out /private/audits

python scripts/generalization_report.py --questions /private/blind.questions.jsonl \
  --rubrics /private/blind.rubrics.jsonl --manifest /private/blind.freeze.json \
  --results /private/comparison/candidate-run/per_question.jsonl --audit /private/audits/run_b.audit.jsonl \
  --baseline-results /private/comparison/baseline-run/per_question.jsonl \
  --baseline-audit /private/audits/run_a.audit.jsonl --campaign /private/comparison \
  --gate --out results/phase4/semantic-comparison.json
```

For development, prepare one `--results` file and omit `--paired-results`; collection yields
`run_a.audit.jsonl`. A development report without `--gate` is diagnostic and may be iterated.
The blind scoring tool prints aggregate outcomes only; it has no per-item miss-table option.
