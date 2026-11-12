# Evaluation record

## Phase 4 reviewed candidate — not promoted

The final corrected development candidate (v7) was verified on November 11, 2026. Independent review binds
59 runtime/data files to manifest `96222efe862a559ba76a40943e5f684fe2722a3aa407d20a96204d30549b654c`.
The publication manifest is `f585d7c0233a024cab10e523fd9e1bd05601c95e3bde79ace0ea066b52f3187a`:
only trailing blank lines were removed from two modules after measurement; their parsed syntax trees match
exactly and the other 57 files are byte-identical. No behavior or source data changed.
The immutable `submission-v1` commit `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38` remains the grading fallback.
**The new blind comparison is unrun, so Phase 4 is not approved for grading.** Public QA does not establish
generalization or the organizers' hidden score.

| Final candidate check | Verified result |
| --- | --- |
| Public QA/final, 40 questions | 0.9690 / 0.9690 |
| Original development QA/final, 20 questions | 1.0000 / 1.0000 |
| Generated proxy QA, 1,300 questions | 0.9976; every family gate passes |
| Previously perfect answers preserved | Public 39/39; original dev 20/20 |
| Nonsealed regression suite | 1,009 passed; two sealed-data readers deselected; holdout test module excluded |
| Python compatibility | Actual 3.9.6 and 3.11.14; identical answers on all 60 public/dev questions |
| Source references / exact source pins | 1,794/1,794 / 1,602/1,602 |
| Curated conflicts | 22/22 source-verified |
| Conflict precision / F1 / resolution | Exact 10/11; 20 of 22 conflicts matched |
| Public with separate development conflict gold | 0.9600 final |
| Answer p95, Python 3.11 / 3.9 | 1.036 ms / 1.440 ms |
| Ingestion, Python 3.11 / 3.9 | 4.30 s / 5.65 s; within the harness limit |

All ordinary runs had zero errors and stale-trap hits. The runtime remains standard-library-only and offline;
53 runtime Python files passed the Python 3.9 grammar and under-500-line checks. Benchmarks used the 40 public
questions; timings are measurements on this host, not universal guarantees.

The small proxy change from the fallback's 1.0000 is explained, not rebaselined: three membership wording
cases have apostrophe token-normalization differences and three conditionally free Bill Pay answers differ
from the older dollar-token expectations. Sources and semantic conditions remain verified; proxy fixtures and
all family thresholds are unchanged.

## Broader development generalization

Independent source authors froze 196 question wordings in 98 scenarios/claim clusters, across eight families.
The source-audited blind set has 148 wordings in 74 scenarios/clusters and remains unrun. The original 120/80
scenario budgets were targets, not achieved sample counts.

| Broader development measure | Frozen fallback | Final candidate |
| --- | ---: | ---: |
| Official token QA (diagnostic) | 0.05125 | 0.286305 |
| Primary family-macro semantic success | 0.000000 | 0.155556 |
| Fully correct individual questions | 0/196 | 45/196 |
| Fully correct paired scenarios | 0/98 | 16/98 |
| Reviewed unsupported confident claims | 73 | 0 |
| Accepted citation failures | 22 | 0 |
| Accepted temporal failures | 14 | 0 |

Final candidate known-stale claims, runtime errors and raw trap hits were zero. A scenario passes only when
both phrasings are individually correct and semantically consistent. The primary macro equally weights the
six families with at least ten independent clusters; it is not simply 16 divided by 98. Its cluster-bootstrap
interval is approximately 0.0889–0.2222. The all-sampled-family macro is 0.155357.

Final judgments reused only **exact question/rubric/answer/error-bound whole pairs** previously reviewed
independently: 188 records from the v6 review and eight restored records from the v5 review. Both members of
every pair matched a prior reviewed pair. There were no new or unreviewed bindings, automatic entailment
judgments, or changed gold labels. Source-review packs, questions and per-item results remain local.

| Family | Fully correct scenarios |
| --- | ---: |
| Product descriptions and purpose | 3/15 |
| Complete eligibility | 1/6 |
| Fee/service terms | 0/14 |
| Organization/count/recognition | 5/15 |
| Branch/contact/status | 0/11 |
| Procedures/navigation | 2/15 |
| Historical/changed prose | 4/15 |
| Ambiguous/unsupported | 1/7 |

The candidate refused 116/196 questions; only two refusals matched the expected unanswerable cases. It answered
77/190 answerable questions. Conservative refusals avoid unsupported assertions but still fail answerable
questions. **Coverage and completeness remain substantial gaps.** The development result is far below the
0.85 target reserved for the final blind release gate.

## Source scope and experiment decisions

The catalog has 397 entries. Its reviewed-requirements census has 654/680 complete source rows, leaving
24 historical conditional-fee scopes and two older advisor scopes incomplete. This is a bounded source census,
not website-wide coverage or an answer score. See [source coverage](phase4/SOURCE_COVERAGE.md).

Both optional routing flags remain off. The original six-arm ablation produced no answer changes; a later
unknown-topic arm added one unapproved answer. A subsequent isolated source-context variant reproduced the
disabled candidate exactly and added no recovery attributable to its new mechanism. It was rejected.
No paid/model-based builder, runtime SDK, API key or model download was introduced.

Independent code review covered typed claims, complete groups, fee conditions, source identity, temporal and
provider boundaries, scoped conflict notes, ranking versus recognition counts, and modified test expectations.
The final guard restored six independently correct answers while preserving the six relevant refusals and
wrong-provider/year controls. Those restoration checks were independently executed; additional automated
versions were not saved before the implementation-agent interruption. The existing suite and review receipts
remain separate evidence.

## Pending release gates

The final [protocol](phase4/EVALUATION_PROTOCOL.md) requires one immutable baseline/candidate blind pair,
primary semantic macro at least 0.85, positive paired improvement, applicable family floors, no family
regression, sparse-family all-pass outcomes, and zero reviewed unsupported/stale/citation/temporal failures.
The steward has verified the frozen source hashes and independent attestation. No campaign is registered and
neither blind execution has launched. Independent review capacity must be available before starting it.

The reviewed implementation can be inspected on the Phase 4 branch, but it is not a new grading release.
An exact-SHA GitHub clone in a clean Python 3.11 environment is also required and is recorded separately in
the submission handoff. Do not infer that check from the helper's default local clone. Keep `submission-v1`
immutable, and change the email's grading SHA only after release approval. See the
[plan-versus-implementation matrix](phase4/IMPLEMENTATION_REVIEW.md).

## Historical Phase 3 fallback

The initial public export preserved the verified Phase 3 runtime and derived catalogs byte-for-byte.
Packaging excluded supplied snapshot archives, documented local kit setup and added the external
`--snapshots-zip` fresh-clone input. The organizer harness and public evaluation remain unchanged.
The following results describe that fallback, not the Phase 4 candidate:

| Evaluation | Recorded result |
| --- | ---: |
| Public final, 40 questions | 0.9690 |
| Original development QA, 20 questions | 1.0000 |
| Generated proxy QA, 1,300 questions | 1.0000 |
| Blind holdout QA / final, 414 questions | 0.9647 / 0.9597 |
| Locked QA / final, 28 questions | 0.0933 / 0.0933 |
| Conflict precision / F1 / resolution accuracy | 0.9091 / 0.9091 / 0.9091 |
| Public with separate development conflict gold | 0.9600 |
| Answer p95 benchmark | 0.631 ms |

The verified runtime passed 522 tests, source checks (238/238 prose references, 22/22 conflicts), and clean
Python 3.9/3.11 clones. Public/dev runs had zero errors or stale-trap hits. No previously perfect public/dev
item regressed against earlier baselines. The committed [baseline](../results/baseline.json) retains this
measurement context; public packaging validation and the grading commit are recorded in the final handoff.

On November 11, 2026, the public export passed **525 tests in 119.21 seconds**, including three new packaging
checks for missing or invalid local kit input. Fresh public/dev runs reproduced **0.9690 / 1.0000**, with zero
errors/stale traps, and the prose/conflict source checks again verified **238/238 / 22/22**. No sealed set was
rescored for the export.

The public command does not supply conflict gold, so its final score excludes that pillar. Public item
`dup-005` has an empty required-token list and scores zero under the deterministic scorer without the optional
semantic judge. All recorded scores use the no-key path; the organizers' hidden evaluation remains unknown.

The historical independent checks exposed substantial generalization limits. Blind description QA was 0.4095,
eligibility and count QA were 0.6667, and paraphrase consistency was 0.9412. The locked score did not improve
in Phase 3. Its description/eligibility curation covered 41/44 eligible products, not the whole website;
IRA Certificate, Variable IRA and personal You Name It Savings were uncovered. Percentage-only and free fee
services were outside that dollar-fee extractor's scope. These limits motivated Phase 4; source expansion
alone does not demonstrate that its answer-quality gates pass.

Locked and blind holdout sets were each scored once per implementation phase, with only aggregate results
read. They were not used for post-score tuning and were not rerun for the public packaging change. Phase 4
uses independent source-grounded development work and a separately controlled blind comparison. Any permitted
final legacy-set run remains aggregate-only and is not a substitute for the new semantic gates.
