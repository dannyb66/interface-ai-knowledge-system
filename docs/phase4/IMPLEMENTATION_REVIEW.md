# Phase 4 implementation review

The corrected v7 implementation and ordinary verification are complete. **The candidate is unpromoted.**
The immutable `submission-v1` tag at `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38` remains the grading fallback.
The final [evaluation record](../EVALUATION.md) binds 59 runtime/data files to independently reviewed manifest
`96222efe862a559ba76a40943e5f684fe2722a3aa407d20a96204d30549b654c`.
The final publication manifest is `f585d7c0233a024cab10e523fd9e1bd05601c95e3bde79ace0ea066b52f3187a`;
its only source difference is trailing blank-line removal in two modules, with identical parsed syntax trees
and all other runtime/data bytes unchanged.

The candidate passes 1,009 nonsealed tests, public/original-dev/proxy QA 0.9690/1.0000/0.9976, source and
conflict checks, actual Python 3.9/3.11 parity and the runtime limit. Independent broader development review
passes 45/196 questions and 16/98 scenarios, primary macro 0.155556, with zero reviewed unsupported, stale,
accepted citation or temporal failures. This still shows substantial generalization gaps. The blind
comparison remains unrun; no new grading tag is approved.

“Implemented” below means the mechanism exists in the current source and documented contracts. It does not
waive final regression or independent semantic acceptance. “Pending” marks a release gate; conditional work
may be closed without adoption when its evidence does not justify activation. The
[approved plan](../plans/2026-11-11-phase-4-generalization.md) remains the historical scope and decision record.

| Item | Current implementation and evidence | Status / remaining work |
| --- | --- | --- |
| P4-01 — Execution setup and immutable reference | Isolated Phase 4 branch/worktree; unchanged fallback tag; [baseline](BASELINE.md) records tests, public/original-dev/proxy, source/conflict checks and committed-clone measurements before runtime changes. | **Baseline complete.** The final candidate has a separately bound runtime/data manifest; baseline evidence remains distinct. |
| P4-02 — Allowed APIs and patterns | `solution.build()` retains the organizer interface. Immutable `Query`, normal resolver, structured `AnswerPlan`, numeric grounding and full-query caching remain boundaries. [Runtime contracts](RUNTIME_CONTRACTS.md) document the implemented extensions. | **Implemented and documented.** Final permitted full-diff/API review passed. |
| P4-03 — Source inventory without alias loss | `scripts/phase4_inventory.py` and `scripts/phase4_sources.py` retain manifest identity, actual crawl, raw/canonical URLs, content hashes and source classes. Runtime `source_pages.py` preserves distinct captures. Detailed source inventories remain local. | **Implemented.** Do not publish source pages or local review extracts. |
| P4-04 — Independent development and blind scenarios | Source-audited sets contain 98 development scenarios and 74 blind scenarios, versus the 120/80 budget targets. Source-gold adapters validate provenance, paired wording, clusters, IDs and hashes; blind artifacts remain steward-owned. The [protocol](EVALUATION_PROTOCOL.md) separates authorship, review and runtime output. | **Source audit complete; blind unrun; final comparison freeze pending.** Bind final source-review attestations and sealed inputs through the steward. Budget targets are not achieved sample counts. This document contains aggregate status only. |
| P4-05 — Richer reporting outside the harness | `generalization_audit.py`, `generalization_report.py` and `generalization_ledger.py` implement explicit semantic review, clustered aggregation/uncertainty, paired gates and the fixed two-role campaign. Organizer scoring is unchanged. The final development review uses exact-bound, independently reviewed whole answer pairs. | **Tooling and final development review complete; blind acceptance pending.** v7 has primary macro 0.155556 and zero reviewed safety failures. Token QA and source matching cannot substitute for independent judgments. |
| P4-06 — Parser/refusal evidence | `diagnostics.py` and parser/selection hooks record explicit, inferred, default and absent evidence, candidate decisions and typed refusal reasons. | **Implemented.** Traces describe runtime choices, not independent truth. |
| P4-07 — Stage attribution and facade parity | `KnowledgeSystem.explain()` follows answer parsing, resolution, rendering and conflict-note handling without mutating the answer cache. `diagnose_generalization.py` validates development-only manifests/IDs/hashes and emits local diagnostics. | **Verified.** Answer/explain parity holds on all 196 broader development questions; diagnoses remain hypotheses until checked against source evidence. |
| P4-08 — Coverage matrix and source quality | `source_coverage_report.py` measures entity/attribute/complete-group/crawl requirements with hash-bound independent attestation. Source quality, raw variants, publication/effective dates and omitted aliases are checked. | **Reviewed source coverage available.** Current aggregate is 654/680 complete rows; 26 historical gaps remain. Rebind attestations if final catalog or registry changes. |
| P4-09 — Versioned semantic annotations | Schema 2 preserves source pins, revision, roles, comparators, bases, units, conditions and required group membership through serialization and selection. Scalar fee conditions, dated attribution and complete description/procedure groups extend the original proposal within the same resolver/grounding path. | **Implemented.** Meaning still requires independent source and answer review; schema validation is not entailment. |
| P4-10 — Bounded content additions | Reviewed catalog expansion has 397 entries, 1,794 entry/page/crawl pairs and 1,602 exact source pins. Complete groups refuse after source/selection loss. Scoped fees, procedures and dated organization prose are bounded by [source coverage](SOURCE_COVERAGE.md). | **Source review and ordinary integration checks complete.** Keep 24 historical fee scopes and two older advisor scopes explicitly incomplete; the final runtime/data manifest binds the artifacts. |
| P4-11 — Diagnose before retrieval | Development/source-led grammar and scope work includes purpose wording, programs, procedures, unsupported modifiers, source/year selection, serving cutoffs and complete compound prose. Source-led triage separates known-fact topic misses from incomplete catalog evidence. Recognition guards now distinguish ranking position, occurrence counts, provider/year scope and background source context. | **Implemented and independently reviewed.** Six valid answers restored exactly; unsupported rank/provider/year requests refuse. Broader coverage remains limited. No full-question dispatch or blind-driven tuning is claimed. |
| P4-12 — Source-derived routing index | `lexical_index.py` builds deterministic verified entity/attribute scopes from ingested sources and registry vocabulary; no evaluation input or query-time index build. The earlier six-arm ablation produced no answer changes. Frozen historical v3 produced identical off/known-topic outputs on all 196 development questions; unknown-topic routing added one confident answer. | **Experiment decision complete; not adopted.** One extra unapproved answer did not establish a safe release gain. Both routing flags remain off; no separate generated-question artifact is claimed. |
| P4-13 — Refusal-preserving arbitration | `routing.py` preserves direct routes, original wording/slots and full-query cache semantics; hard refusals, unsupported qualifiers and excluded historical/compound scopes cannot be overridden. Normal resolution still selects facts. | **Guarded experiment implemented, disabled.** `lexical_routing=False` and `unknown_topic_routing=False` are the candidate defaults. |
| P4-14 — Verified-fact fallback experiment | The optional index already targets verified fact scopes. An isolated source-context variant had disabled output exactly matching v5; enabled output changed only the pre-existing unknown-topic answer. No answer recovery was attributable to the new source-context mechanism. | **Isolated variant rejected; no additional fallback adopted.** The experiment did not change the working runtime or justify relaxing guards. All routing flags remain off. |
| P4-15 — Offline model prose builder | `build_reviewed_candidates.py` deterministically expands independently reviewed seeds over matching source variants. It is not a model generator and does not call an API. | **Model experiment not activated.** No paid/model builder, SDK, key or grading-time model dependency was introduced. |
| P4-16 — Development acceptance and adversarial review | Final v7 preserves public/original-dev 0.9690/1.0000 and all 39+20 perfect items; proxy 0.9976 passes every family gate. 1,009 nonsealed tests pass, two sealed readers are deselected and the holdout module is excluded. Actual Python 3.9/3.11 answers match on 60/60 items; all source/conflict and runtime gates pass. Independent development primary macro is 0.155556 with zero reviewed safety failures. | **Ordinary development verification complete; generalization remains limited.** These are development measurements, not a blind release pass or full sealed-suite claim. |
| P4-17 — One predeclared blind comparison | The ledger can bind exact baseline/candidate commits, inputs, source review and scorer/launcher hashes, then consume one baseline and one candidate execution. | **Pending gate; zero launches.** Steward verified the frozen source hashes and independent attestation. Restore independent review capacity, register the frozen pair, and apply all predeclared semantic/family/safety gates. A failure retains the fallback rather than allowing iterative blind tuning. |
| P4-18 — Public release and handoff | README, NOTES, evaluation record and [submission instructions](../SUBMISSION.md) describe the candidate and exact-SHA reproduction. Privacy rules exclude supplied snapshots, archives, keys and private audit/evaluation artifacts. | **Reviewed handoff prepared; release pending.** Safe privacy preflight and final measured docs are complete. Record the pushed candidate SHA and its exact-SHA GitHub clone check separately; a new grading tag still requires the blind gate. Do not move `submission-v1`; emailing remains a separate user action. |

## Implemented behavior and bounded scope

Source verification retains actual crawl/raw URL/content identity; distinct captures cannot lend one another
quotes, dates or scoped fee footnotes. Complete eligibility, procedure and declared description groups retain
every required claim through verification, selection and rendering. Missing conditions do not become complete
answers. AND/OR, bounds, units, named bases and customer/service qualifiers remain explicit.

Dated prose keeps publication or event attribution. Loan APR/rate tables headed “As Low As” preserve that
bound, suppress exact personal-rate verdicts and retain table citations. Conflict notes require the selected
product/attribute/tier and an applicable answering date, then add supporting sources. Compound prose covers
only eligibility plus service information for one recognized entity; both normal resolver arms must succeed.
It does not authorize arbitrary multi-entity or numeric composition or personal eligibility decisions.

The implementation keeps article publication/year selection separate from the serving `as_of`
cutoff, require every requested attribute in a historical branch bundle, and preserve planned-event wording
without asserting that an event occurred. An unknown named lab/location cannot become a generic branch list.
Current-resolution conflict notes must not be appended to a historical-source-context answer. Unknown
providers, unsupported amounts and cash-advance scope must survive parsing and selection. These are required
semantics verified in the final candidate. Recognition frequency cannot supply a ranking position; explicit
provider/event-year checks preserve complete typed background context and distinguish article publication dates.
Unsupported “up to/by” recognition-date wording remains a conservative refusal limitation.

The current 654/680 source matrix is a reviewed-requirements census, not a website-wide or semantic success
score. Both optional routing flags are off, and no model builder was activated. These decisions preserve the
planned refusal and offline constraints with measured development improvement and explicit limits; they do not establish blind generalization.

## Promotion evidence still required

Record the clean pushed candidate commit alongside the final runtime/catalog/registry/schema/scorer hashes.
The catalog/registry source attestations remain unchanged and all ordinary gates pass. Preserve the exact
conflict baseline 10/11, not a rounded threshold. An exact-SHA GitHub clone is packaging evidence, not a
substitute for the remaining independent comparison.

Then register the steward's one frozen baseline/candidate comparison and review only its aggregate release
outcome. Require primary semantic macro at least 0.85, positive paired improvement, applicable family floors,
no sampled-family regression, reserved sparse-family all-pass outcomes and the zero-failure safety gates in
the [protocol](EVALUATION_PROTOCOL.md). Source coverage and official token QA cannot replace these gates.

Finally clone GitHub, detach at the full frozen grading SHA and assert HEAD before creating a clean Python
3.11 environment and providing the external participant kit. Run the unchanged guarded harness and source
checks; verify stricter Phase 4 performance separately. The existing fresh-clone helper has no `--ref` or
expected-SHA support and checks 500 ms, not the Phase 4 50 ms limit. Publish only measured final results and
known limitations after these checks, leaving the immutable fallback intact.
