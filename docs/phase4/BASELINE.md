# Phase 4 baseline

Phase 4 implementation was approved on November 11, 2026. The isolated branch is `phase-4-generalization`, based on immutable `submission-v1` commit `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38`.

These are fresh pre-implementation measurements, separate from the historical Phase 3 record. No runtime file differed from the baseline commit during these checks. Python 3.11.14 ran in an isolated local environment; the supplied kit remained in ignored local symlinks.

| Check | Result |
| --- | --- |
| All tracked baseline tests | 525 passed in 119.86 seconds |
| Public QA/final, 40 questions | 0.9690 / 0.9690 |
| Development QA/final, 20 questions | 1.0000 / 1.0000 |
| Generated proxy QA/final, 1,300 questions | 1.0000 / 1.0000; family gate passes |
| Public with development conflict gold | 0.9600 final |
| Conflict precision / F1 / resolution accuracy | 0.9091 / 0.9091 / 0.9091 |
| Prose source references | 238/238 verified |
| Curated conflicts | 22/22 verified |
| Fresh committed clone, Python 3.11 | Pass; public final 0.9690 |
| Answer benchmark, 40 public questions | p50 0.305 ms; p95 0.614 ms; max 1.331 ms |

Public, development, proxy and conflict runs had zero errors and stale-trap hits. Ingestion stayed within the harness limit. All recorded command exit codes are zero. Tests, evaluation and source/fresh-clone checks ran concurrently, so timing reflects shared host load. The dedicated benchmark provides finer timing than the rounded harness report.

No locked or holdout evaluation was run. Existing sealed integrity tests executed within the full test suite, with output inspected only as an aggregate; no sealed questions, templates or per-item results were reviewed. New untracked Phase 4 tests were excluded by enumerating tracked baseline test modules.

The ignored local evidence directory `results/phase4/baseline/` contains command logs, ordinary evaluation reports and `manifest.json`. The manifest records the baseline commit/tree, Python version, 51 file hashes covering runtime/catalogs, scorer/tooling and nonsealed datasets, five source-manifest hashes, exact commands, outcomes and the approved plan hash. It identifies the absent routing-index artifact explicitly. Source snapshots and private evaluation material remain outside Git.

## Confirmed runtime contracts

- `parse(...)->Query` remains the immutable parsing boundary; the actual answer cache uses the entire `Query`, not its diagnostic canonical key.
- `resolve(q, store, registry)->AnswerPlan` owns temporal, authority, qualifier and tier arbitration. `FactStore.in_force` alone only filters effective dates.
- `KnowledgeSystem.answer` runs parse/cache/resolve/render/conflict-note handling. `explain` is a separate diagnostic facade and currently lacks complete candidate and conflict-note parity.
- `ProseBook.facts(snapshot_id, pages, normalized=None)` verifies page/crawl quotes during ingestion. Its present canonical-URL page mapping needs the planned identity-preserving extension.
- The existing fresh-clone script supports `--snapshots-zip`, but no `--ref`. Final publication must independently check out and verify the frozen remote candidate SHA.

The exact existing signatures and source locations remain in P4-02 of the [approved plan](../plans/2026-11-11-phase-4-generalization.md). Baseline setup introduced no runtime changes and did not change the published submission tag.
