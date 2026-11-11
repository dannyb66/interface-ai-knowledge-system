# Evaluation record

The public export preserves the verified Phase 3 runtime and derived fact catalogs byte-for-byte. Packaging
changes exclude private snapshot archives from Git history, explain local data setup and extend the fresh-clone
check with a local `--snapshots-zip` input. The organizer harness and public evaluation are unchanged.

| Evaluation | Recorded result |
| --- | ---: |
| Public final, 40 questions | 0.9690 |
| Development QA, 20 questions | 1.0000 |
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

The independent checks expose substantial generalization limits. Blind description QA is 0.4095, eligibility
and count QA are 0.6667, and paraphrase consistency is 0.9412. The locked score did not improve in Phase 3.
Description/eligibility curation covers 41/44 eligible products, not the whole website; IRA Certificate,
Variable IRA and personal You Name It Savings remain uncovered. Percentage-only and free fee services are
outside the dollar-fee extractor's scope. Unsupported requests remain refusals.

Locked and blind holdout sets were each scored once per implementation phase, with only aggregate results
read. They were not used for post-score tuning and are not rerun for this packaging change. Future changes
should use independent source-grounded development questions and separate blind validation.
