# Phase 4: Generalization — implementation plan

Status: **approved for implementation; in progress**. Approved November 11, 2026.

## Primary goal

Answer unfamiliar, source-supported questions about the supplied website accurately and completely, including descriptions, eligibility, fees, organization information and historical changes. Improve independent generalization while preserving the existing rate/tier accuracy, grounded citations, conservative refusals and offline operation.

The published fallback is commit `5d35aaf9e661c384e9ad9d67a6c2705ec98b0b38`, tag `submission-v1`, in `dannyb66/interface-ai-knowledge-system`. Keep that tag immutable. All measurements below are recorded Phase 3/public-packaging results, not new runs for this planning session.

## Why this phase exists

| Evidence | Interpretation |
| --- | --- |
| Public 0.9690; dev and generated proxy 1.0000 | Preserve these regressions. They do not establish broad website coverage. |
| Blind description 0.4095 on 21 questions | A material generalization weakness; aggregates do not identify its failure stage. |
| Blind eligibility/count 0.6667 on three questions each | Weak evidence with very small samples; expand independent measurement. |
| Blind paraphrase consistency 0.9412 | Wording robustness needs attention, even under the existing numeric-set metric. |
| Locked 0.0933, unchanged | Broad unseen-question performance remains unresolved. Never infer the official hidden score from public performance. |
| 41/44 products have description **or** eligibility | Presence metric only: static catalog inspection finds descriptions for 39/44 and some eligibility text for all three declared eligibility products. This is not eligibility completeness or website coverage. |
| Answer p95 0.631 ms; 525 tests pass | Speed is not the current score bottleneck. Preserve the tested runtime guarantees. |

Source evidence found during read-only discovery:

- Five missing descriptions, not merely three: `ira_cert`, `ira_variable`, `you_name_it_savings`, `membership`, and `mortgage_rate_relief`. The last two are hidden by the coverage metric's OR condition. Add only what the supplied sources actually support.
- The dollar-only fee extractor omits free/no-charge and percentage services, including conditional membership pricing.
- The Mortgage Rate Relief source contains a percentage eligibility threshold and a distinct percentage-point benefit. Current curation covers only part of eligibility, and its schema rejects `%` in eligibility quotes. Preserve the source's exact named basis; do not relabel it using outside financial knowledge.
- Undated organization pages contain relevant information outside the current narrow prose extractor.
- A latest organization page has broken rendered counters, including `NaN` and zero counters. Quote occurrence alone does not establish reliable evidence.
- Canonical-URL dictionaries can overwrite multiple manifest entries. Latest crawl: 705 manifest pages, 697 distinct canonical URLs. Inventory must retain identities before grouping aliases.

These observations are not diagnoses of individual sealed failures. No sealed questions or templates were read and no evaluations were run for this plan.

## Reconciliation with the earlier plan

The development archive's `2026-11-05-phase-3a-conflicts-and-prose-facts.md:136–142` deferred T3 routing unless proxy routing fell below 0.80, made the ET4 builder conditional on catalog coverage/proxy results, and deferred ET9 BM25 outright. Those triggers did not fire. Phase 3 therefore met its approved scope.

Phase 4 proposes a different decision basis: independently authored source truth, complete claims, per-family semantic performance and diagnosed failure stages. It does not retroactively declare the old gates failed.

| Item | Phase 4 decision |
| --- | --- |
| Independent source inventory, evaluation and diagnostics | Required first. |
| Complete verified facts, source-quality checks and bounded schema extensions | Required for demonstrated development/source-audit gaps. |
| Parser robustness and guarded routing | Required workstream; ship the simplest intervention that improves independent development performance. |
| Generated-question index, T3 | Implement a bounded experiment if eligible routing misses persist; adoption is gated. |
| Verified-fact lexical fallback, ET9 | Optional experiment reusing the routing infrastructure; no raw-paragraph answer fallback. |
| Offline model builder, ET4 | Conditional candidate-generation tool. Default first pass uses rules and audited curation; no paid API use is assumed. |
| General “what changed?” without a product | Deferred unless the source-first development set establishes enough demand and an unambiguous bounded answer contract. |
| Runtime LLM, embeddings, multi-site support, UI | Outside this phase. |

## Non-negotiable constraints

1. Runtime remains standard-library-only, deterministic, Python 3.9 compatible, offline and read-only. No SDK, model download, network call or index construction inside `answer()`/`conflicts()`.
2. Preserve the organizer contract, `harness/`, `eval/public_eval.jsonl` and `starter/`. Extend evaluation in separate tools; never modify the official scorer to improve a number.
3. Source snapshots, participant archives, credentials and full private audit extracts stay outside public Git history. Keep the external-kit fresh-clone workflow.
4. Existing locked and holdout items/templates remain sealed. Do not inspect their failures, copy their wording, or use them for iterative tuning.
5. An index can propose a route; it cannot authorize an unsupported fact. Every accepted route still goes through publication/effective dates, authority, segment, product, program and tier arbitration, then `AnswerPlan`, numeric lint and source checks.
6. Keep the entire frozen `Query` as the answer-cache key. Its `canonical_key` is diagnostic and omits distinctions needed for truthful verdicts and refusals.
7. A source quote must support the subject, predicate, conditions and date of a claim, not just contain its numbers. Preserve AND/OR, exclusions, bounds and units.
8. No guaranteed hidden score is promised. Thresholds below are proposed release criteria, not measured outcomes.

## Phase 0 — Documentation discovery and baseline freeze

**How this serves the primary goal:** establishes the behavior that improvements must preserve and prevents planning against nonexistent APIs.

### P4-01: Execution setup and immutable reference

- Create the approved Phase 4 branch/worktree from `submission-v1`. Keep the existing public grading commit and tag intact.
- Save a Phase 4 baseline manifest with runtime commit, registry/catalog/index hashes, Python version, scorer version and dataset hashes. Keep historical Phase 3 metrics separately labeled.
- Run ordinary public/dev/proxy and full regression checks once on the starting checkout when execution begins. Do not rerun old sealed sets at setup.
- Confirm all local kit paths are ignored and the external ZIP option works. Do not copy the private development repository's Git history.

### P4-02: Allowed APIs and patterns

Read these sources before implementation. Line references describe the frozen public baseline and may move after refactoring.

| Existing interface/pattern | Source | Constraint |
| --- | --- | --- |
| `parse(question, as_of, registry, max_chars=1000, reference_date=None) -> Query` | `submission/kb/question.py:279` | Returns the immutable query; parsing currently uses rules/aliases. |
| `Query` | `submission/kb/question.py:75` | Retains original question, numbers, dates, qualifiers and multiple mentions. |
| `resolve(q, store, registry) -> AnswerPlan` | `submission/kb/resolve.py:404` | Required arbitration boundary; current refusal order is at line 412. |
| `FactStore.add/finalize/snapshot_for/in_force` | `submission/kb/store.py:89,105,125,143` | `in_force` filters effective dates only; it does not replace publication/tier selection. |
| `AnswerPlan` and `Fact` | `submission/kb/types.py:39,59` | Keep renderer inputs structured and source-backed. |
| `render_with_dropped(plan)` | `submission/kb/compose.py:317` | Numeric lint, grounding, refusal handling and citations remain mandatory. |
| `KnowledgeSystem.answer/explain` | `submission/kb/system.py:256,282` | Explain is currently incomplete; its candidates are already-selected facts. |
| `parse_prose/load_prose/ProseBook.facts` | `submission/kb/prose_facts.py:39,103,116` | Strict schema and per-page/per-crawl verification; no existing model builder. |
| `page_text/quote_found/value_in_quote` | `submission/kb/verify.py:32,40,46` | Necessary validation, not proof of semantic attribution. |
| `Registry.resolve/published/aliases` | `submission/kb/registry.py:248,289,285` | `Registry.resolve` maps extraction labels; it is not query retrieval. |
| Arbitrary eval path under socket guard | `scripts/_guarded_run_eval.py`; `harness/run_eval.py:110` | `scripts/eval.sh` has named modes, not a generic `--set` API. |
| Exact result-ID validation and family aggregation | `scripts/proxy_report.py:28` | Reuse the pattern, not old family thresholds as new acceptance criteria. |
| External-kit fresh clone | `scripts/fresh_clone_check.sh` | Use `--snapshots-zip`; no data in Git. |

**Verification:** record the actual signatures and current output invariants; all existing regressions pass; public/dev remain 0.9690/1.0000.

**Anti-pattern guards:** no invented retrieval API, no model SDK in runtime, no cache-key simplification, no use of source snapshots as public fixtures.

## Phase 1 — Build independent source truth and evaluation

**How this serves the primary goal:** measures what users can actually ask, including facts the current extractor misses, instead of grading only the system's own extracted facts.

### P4-03: Inventory every source class without losing aliases

Create proposed tool `scripts/phase4_inventory.py` and synthetic tests in `tests/test_63_generalization_inventory.py`.

- Copy the manifest/block/row traversal pattern from `scripts/build_registry.py:35` and `blocks.split_blocks/table_rows` at `submission/kb/blocks.py:279,447`.
- Retain snapshot ID, manifest page index/path, raw and canonical URL, content hash, page class, heading/block location and explicit date evidence. Group aliases only after recording every original identity.
- Include PDFs, product/about pages, newsroom, blog, business resources and listings. Mark navigation, related-article snippets and unsupported page types explicitly rather than silently dropping them.
- Do not reuse `sample_pages.py:24–39` exclusions or the canonical-URL overwrite behavior in `curate_prose_catalog.py:52–60`.
- Keep detailed inventory/excerpts under ignored `results/phase4/`. Publish methodology, schema and aggregate counts only.

### P4-04: Independent development and blind scenarios

Use fresh source-curator agents with no implementation, parser, generated-proxy or old sealed-question context. The current discovery agents must not become the blind authors.

- A dataset steward establishes source/claim clusters before question writing. Cluster aliases, repeated boilerplate, sibling products sharing the same sentence, and all crawl variants of one claim. Keep a claim's paraphrases and temporal variants in one partition.
- Author truth from raw source sections, not `FactStore`, `select_dated`, parser output or generated answers. An independent reviewer verifies each scenario against the source and its date context.
- Initial budget: **120 development scenarios plus 80 blind scenarios**, usually two independently worded questions per scenario: approximately 240 dev and 160 blind questions. These are targets, not permission to manufacture independent evidence.
- Cover eight primary families: descriptions/product purpose; complete eligibility; fee/service terms; organization facts/counts/recognition; branch/contact/status; procedures/navigation; historical/changed prose; ambiguous/unsupported requests. Preserve rate/tier behavior through existing regression suites and added cross-family controls.
- Target approximately 15 dev and 10 blind scenarios per family. Report distinct claim/source clusters separately from question counts. Before development output is seen, assign sparse-family clusters exclusively to development or blind validation. A development-exposed census measures audited coverage and cannot later count as blind evidence, even with new wording.
- Proposed minimum for a numeric blind family gate: 10 independent claim clusters. Declare named sparse-family exceptions and their development/blind allocation in the frozen manifest; do not manufacture independence to meet the quota. Report their exact blind outcomes separately and require every reserved sparse blind scenario to pass. If no blind cluster is available, report the family as independently unvalidated and limit the release claim accordingly.
- Disjoint cluster assignment is the primary split rule. Normalized equality and token-Jaccard checks are additional hygiene, not proof of semantic independence. Audit unavoidable overlap explicitly.
- Freeze source inventory, split seed, scenarios, expected truth, scoring policy and hashes before implementations see development failures. Baseline output must not determine which questions are retained.

Proposed development artifacts: `eval/generalization/dev.jsonl`, a separate claim/rubric file, and an aggregate manifest. New blind questions, labels and per-item results live in a separate ignored/local evaluation directory controlled by the steward. They are not implementation inputs or runtime artifacts.

### P4-05: Richer reporting outside the official harness

Create proposed tools `scripts/generalization_report.py`, `scripts/generalization_audit.py` and a testable run-ledger helper, plus synthetic tests in `tests/test_64_generalization_eval.py`.

Ordinary JSONL retains the existing harness fields. A separate rubric adds:

```text
case_id, family, claim_cluster_id, source_family_id, as_of, answerability
required_claim_ids, forbidden_claim_ids, required_conditions
source_refs: raw/canonical URL, snapshot ID, locator, limited evidence span
expected entity/attribute/date/qualifiers, where independently establishable
```

The official scorer ignores most of these fields. New tooling must explicitly evaluate them; merely adding fields does not create semantic scoring.

- Report official QA separately from semantic correctness, completeness, citation support, answerable coverage, appropriate refusal and unsupported confident claims.
- Review whether answers preserve negation, comparators, AND/OR conditions, units, attribution and temporal applicability. Source presence alone is insufficient.
- Do not treat selected runtime facts or trace explanations as independent gold. They are diagnostic evidence only.
- Use independent, source-grounded answer review for semantic judgments that deterministic checks cannot establish. Reviewers receive frozen rubrics and randomized baseline/candidate outputs, not implementation identity. Disagreements are adjudicated; no external model judge is required by default.
- Report paraphrase equivalence by supported claims/verdicts, not just numeric-set equality. Number-free contradictions must fail.
- Define binary semantic success before scoring. An answerable question passes only if the answer is supported, complete against its required claims/conditions, temporally applicable and correctly cited; an unexpected refusal fails. An unanswerable question passes only with an appropriate refusal and no unsupported assertions. Averaging these dimensions must not turn an incomplete answer into a pass.
- A scenario passes only when every declared wording passes and the verdict/claims are consistent. Average scenario passes within a claim cluster, then give each cluster equal weight within its family. The primary macro is the unweighted mean of families meeting the frozen minimum-cluster rule; report its family names/count and a separate all-sampled-family macro. If no family qualifies, the primary macro is unavailable and the release gate fails; do not substitute the all-sampled macro. Sparse families are never silently dropped or treated as statistically adequate.
- Show raw numerators, distinct clusters and clustered uncertainty; paraphrases are not additional independent facts. Missing labels or unresolved reviewer disagreements block scoring. An expected but empty family without a predeclared exception blocks the comparison.
- Register an immutable blind-comparison manifest containing the dataset hash, baseline commit, candidate commit, rubric/scorer versions and exactly two allowed submissions. The ledger permits only that frozen pair; changing the commit, scoring version, purpose or run label does not open another attempt. Permit a documented infrastructure retry only if it failed before any scoring/output review, with the failed attempt retained in the ledger.

**Verification:** source-review checklist passes; IDs/results match exactly; deliberate wrong-subject, omitted-condition, false-Yes, stale-snapshot and unsupported-citation mutants fail the new audit. Missing-family samples are visible, not silently excluded.

**Anti-pattern guards:** no expected answers from the submission store; no blind miss tables; no filtering questions after seeing answers; no optional network judge in the guarded harness; no claim that token QA or numeric consistency proves meaning.

## Phase 2 — Add diagnostic traces without changing answers

**How this serves the primary goal:** identifies whether a missed answer needs better facts, better routing or better rendering, avoiding broad changes that do not address the actual failure.

### P4-06: Explicit parser and refusal evidence

Add a proposed internal trace contract, with helpers in `submission/kb/diagnostics.py` and parser evidence kept separate from user-facing answer text.

- Record whether entity, attribute, intent and qualifiers were explicit, inferred or defaults. Preserve original question text and numbers.
- Record refusal causes at the existing resolver branches: malformed date, unknown entity, unpublished attribute, unavailable segment/program/qualifier, no eligible crawl/fact, ambiguity and rendering-grounding rejection. Distinguish a withdrawal from a parse miss.
- Keep one arbitration implementation. Instrument or extract existing guards into shared helpers; do not build a second resolver for explain mode.
- Preserve existing `parse` and `resolve` caller compatibility, using optional internal tracing/new helper functions. Any new API is proposed work, not an existing method.

### P4-07: Stage attribution and facade parity

Extend `KnowledgeSystem.explain` and create proposed `scripts/diagnose_generalization.py`.

- Show pre-filter candidate counts/IDs and rejection reasons through source quality, date, authority, segment, qualifier and tier selection; distinguish them from final plan facts.
- Include the final answer's sources and conflict note. Explain currently omits `with_note`, while the answer facade applies it.
- Attribute each development failure to extraction/evidence, entity/intent/qualifier/date parsing, selection, rendering/completeness, or unresolved diagnosis. Ground expected labels in the independent rubric.
- Keep current `parse/resolve/render` timing keys for compatibility, or version the timing contract and update `scripts/bench.py:32` and `tests/test_40_adversarial.py:207` together. Nested routing timings are preferable to breaking the top-level contract.
- Preserve full-`Query` cache semantics, independent returned objects and ingest invalidation. If provenance fields are added to `Query`, explicitly account for fixture serialization and keep semantic canonical keys stable for unaffected questions.

Copy regression patterns from `tests/test_40_adversarial.py:22,35,59,72,81,106,181,201`, including cache twins, uncached parity, hash-seed equality and no index builds during answering. Add `tests/test_65_generalization_trace.py`.

**Verification:** instrumentation-only changes produce byte-equivalent non-timing public/dev answers, citations and conflict notes; existing tests pass; synthetic cases exercise every declared reason. No full source text is logged publicly.

**Anti-pattern guards:** `confident=False` is not a sufficient recovery signal; a plan containing facts may still be a withdrawal/refusal; the first selected fact is not proof of a globally winning candidate.

## Phase 3 — Expand verified coverage and preserve meaning

**How this serves the primary goal:** makes missing supported answers available while preventing broader extraction from importing malformed, stale or misattributed information.

### P4-08: Coverage matrix and source-quality decisions

Extend coverage reporting with a new claim-level report rather than redefining the historical 41/44 metric.

- Track entity × attribute × required claim set × crawl, including description coverage separately from complete eligibility.
- Use development diagnosis and source inventory to prioritize missing facts. Audit the five missing descriptions, but leave them unavailable if the kit does not contain defensible statements.
- Add a source-quality module/helper for nonfinite values, broken rendered counters, unclear subject, missing units, ambiguous dates and incomplete clauses. Quarantine uncertain candidates for review instead of admitting them by latest-crawl priority.
- Distinguish legitimate zero/free fees from broken organization counters. Never infer that every zero is invalid or every latest page is authoritative.
- Retain a canonical-URL multimap through runtime ingestion and curated/conflict verification. `system.py:180–186` and `ProseBook.facts():116` currently collapse each canonical URL to one page. Verify against the exact snapshot, raw URL, manifest identity and content hash; cite the actual supporting raw page. Normalize/cache by source identity or verified identical content, never by canonical URL alone. Quarantine unresolved conflicting variants, and prove manifest-order independence with different-content collision fixtures.

### P4-09: Versioned semantic annotations for constrained prose

Write a short schema contract before code changes. Prefer a backward-compatible v2 extension of the existing curated-entry pipeline over a second unrelated fact store.

- Preserve v1 entries and their exact validation. Add explicit semantic annotations only where needed: numeric role, comparator, named basis/denominator, condition-group identity and source-preserved logical wording.
- Recommended runtime transport: a versioned immutable semantic annotation attached to `Fact` as an optional field with a v1-compatible default. Define stable claim identity, source/crawl-specific revision, comparator/basis and condition grouping; selected facts carry it through `AnswerPlan` into rendering. Extend serialization/deserialization explicitly, including old-record defaults and ingest/cache invalidation. Build-time-only metadata is insufficient.
- Keep `Fact` qualifier values scalar. Nested audit/condition metadata belongs in the validated semantic annotation, not inside `FactKey` qualifiers. Conditions that affect fact selection also need explicit scalar query/fact slots.
- Preserve effective dates for fees. Current `ProseEntry` has no effective date and emits `Fact.effective_date=None`, whereas `extract_fees.py:54–64` preserves it. Add validated v2 date support or retain the fee extractor's dated path; never convert a future fee into an immediately applicable assertion.
- Specify membership/service-condition slots across registry validation, question parsing, resolver filtering and composition before adding conditional facts. Explicit member/nonmember or service conditions are hard filters. With an omitted class, return a bounded, fully supported schedule with conditions labeled only if every applicable alternative is known; otherwise request clarification through the existing conservative refusal path. Never silently choose a customer class or lowest price.
- Permit percentage eligibility only through a reviewed eligibility-condition role with exact source support. Keep ordinary descriptions from acquiring unrelated advertised rate numbers.
- Treat percent, percentage points, money, counts and textual “Free/No charge” as different meanings. Do not turn a rate reduction into a published APR or invent `$0` when the source only says “Free.”
- Preserve the complete source condition, including named basis, exclusions and AND/OR logic. Phase 4 states published eligibility; it does not become a general personal-eligibility decision engine.
- Extend registry capabilities only alongside supporting source facts and tests. New supported attributes must remain distinct from unpublished loan/rate attributes.
- Approved facts retain strict numeric checking and full crawl/page provenance. New extractor labels must not accidentally bypass `STRICT_EXTRACTORS`; default to reviewed curated facts with candidate-generation provenance recorded separately.

### P4-10: Bounded content additions

Implement from verified source evidence and diagnosed development gaps:

1. Complete program/membership eligibility where the supplied source states it; explicitly preserve unknown details where linked pages are absent.
2. Free/no-charge, percentage and conditional fee rows. Represent member/nonmember and other service conditions as hard scope. Handle simple cases first; unresolved compound/minimum/maximum formulas refuse rather than borrowing another price.
3. Relevant organization descriptions, ownership/founding/leadership and source-supported counts, with publication/context rules appropriate to each claim.
4. Selected procedures/navigation and product features that independent development questions require. Keep instructions complete enough to answer, without retrieving unrelated page text.

Primary files: `submission/kb/{system,prose_facts,types,extract_fees,article_facts,registry,question,resolve}.py`, sourcebook/serialization and composition helpers, and `submission/data/{products,prose_facts}.json`; introduce focused helper modules before exceeding the repository's 500-line limit. Agree source identity, semantic transport and hard-condition contracts before parallel coverage/routing edits.

Copy quote/source-set expansion from `scripts/curate_prose_catalog.py:66`, but replace canonical-URL overwrites with the Phase 1 inventory. Copy verification and historical-source tests from `tests/test_16_prose_facts.py:38–119`, fee examples from `tests/test_12_fees.py:55`, and eligibility ordering/history from `tests/test_47_curated_answers.py:21`. Add focused `tests/test_66_claim_semantics.py` and `tests/test_67_source_quality.py`.

**Verification:** every added fact independently reviewed; all declared page/crawl quotes verify; no omitted known matching source; complete development claim sets satisfy their rubrics; source-quality mutants are quarantined; original public/dev and strict numeric safeguards remain intact. Exercise reversed manifest order, colliding raw pages, future effective fees, member/nonmember/unspecified class and additional service conditions. End-to-end tests must catch a dropped condition or percent/percentage-point confusion after ingestion and serialization, not just during catalog validation.

**Anti-pattern guards:** no blanket `%` allowance, no inferred external financial definitions, no synthesized zero prices, no partial eligibility presented as a complete decision, no sibling-product borrowing, no model confidence replacing evidence.

## Phase 4 — Generalize parsing and guarded routing

**How this serves the primary goal:** lets unfamiliar wording reach existing verified facts without letting an approximate match override explicit user constraints.

### P4-11: Diagnose before introducing retrieval

- Use only new development cases to distinguish known-fact routing misses from missing facts. Fix broadly supported wording/alias patterns first; preserve prior typo-protection and URL-context repairs.
- Add regression tests for whole classes: purpose/use-case wording, eligibility variants, indirect fee questions, historical prose and negated/contradicted claims. Do not add literal full-question dispatch rules.
- Compare each repair against the frozen baseline at the item and family level. Do not update fixture truth silently.

### P4-12: Source-derived routing index, if eligible misses remain

Proposed new modules: `submission/kb/routing.py`, `submission/kb/lexical_index.py`; builder/validator tools under `scripts/`; a versioned artifact under `submission/data/`. These do not currently exist.

- Index independently generated question surfaces and/or verified claim descriptions derived from source facts, registry aliases and approved vocabulary. Never ingest development, proxy or sealed evaluation questions into the routing artifact.
- Each entry proposes an **entity/attribute/intent scope**, with any source-backed hard constraints and provenance. It does not contain an answer to emit. Eligibility must route to the complete applicable condition set, not one lucky sentence/item.
- Collapse multiple paraphrases for one target before measuring ambiguity. The top-two margin compares distinct target scopes, not two surfaces of the same target.
- Use a small deterministic standard-library lexical ranker. If BM25 is adopted, document tokenization and scoring; its score is not a probability. Calibrate threshold and distinct-target margin on development positive and negative controls only.
- Build/load indexes during initialization/ingestion and validate referenced targets against ingested facts. Keep index generation/version and candidate scores in diagnostics; no query-time rebuilds or file reads.

### P4-13: Refusal-preserving arbitration

Recommended order:

```text
parse original question and explicit constraints
    → reject malformed/explicitly unsupported requests
    → retain unambiguous direct route
    → consider an alternative only for a declared recoverable ambiguity/default
    → accept a unique compatible route above frozen thresholds, otherwise abstain
    → run the existing temporal/authority/qualifier/tier resolver
    → build AnswerPlan → render → numeric/grounding checks → citations
```

- Initial recovery scope is recognized entities with unclear/defaulted attribute or intent. Unknown-entity recovery is not automatic; add it only as a separately evaluated extension with evidence-backed aliases and explicit unknown-entity negative tests.
- Never recover an explicit unpublished attribute, unsupported program, wrong segment, missing tier, invalid date or withdrawn claim by choosing a nearby fact.
- Preserve original wording/numbers when applying a route; do not reparse a generated question as if the user asked it. Implement a tested route-application helper with an allowlist of field transitions. Reconcile derived fields such as `generic_rate`, `past`, `as_of_end`, `change_point`, `product_ids`, `families` and `mentions`, and rebuild diagnostic canonical keys consistently. Initially exclude multi-mention/historical transformations that cannot preserve their explicit semantics; changing only `attribute` is unsafe because `_column()` can override it when `generic_rate` remains set.
- Cache the result under the original full query in the same immutable index generation; clear answers when ingestion changes the index. Do not merge semantically different yes/no claims through a reduced cache key.
- A disabled/default configuration must reproduce the existing path. Use construction-time configuration for ablations, not an undocumented grading environment switch.

Add `tests/test_68_guarded_routing.py` and `tests/test_69_routing_safety.py`, copying refusal, tier, temporal and cache patterns from the Phase 0 reference table.

**Verification:** development semantic performance improves on eligible misses; explicit hard-refusal controls are unchanged; accepted-route errors are zero on the audited negative controls; deterministic tie handling, no query-time index work and p95 below 50 ms. Preserve existing public/dev perfect items.

**Anti-pattern guards:** no raw paragraph output, no approximate match that erases a hard slot, no “nearest result always wins,” no canonical-key-only caching, no threshold selection from blind results.

## Phase 5 — Run optional experiments only where diagnosis supports them

**How this serves the primary goal:** tests broader mechanisms against concrete remaining failures without making them prerequisites for a reliable submission.

### P4-14: Verified-fact fallback experiment

- Reuse the same lexical index and guarded route contract to search verified fact scopes when generated-question surfaces miss.
- Filter by the applicable crawl and explicit entity/segment/program/attribute/qualifier constraints. The existing resolver still selects publication, authority and tiers.
- Propose a compatible route only, then invoke the existing `resolve()`. The resolver alone selects facts and constructs `AnswerPlan`, including permitted numbers, source expansion, withdrawal behavior and temporal metadata. Never construct a second selection path or emit a retrieved paragraph.
- Record an ablation: baseline; coverage-only; routing-only; combined; combined plus fallback. Adopt fallback only for additional semantic wins without new unsupported/confident, stale, citation or refusal failures.

### P4-15: Offline prose-builder experiment

- Activate only when the independent audit finds enough missing, source-supported claims that rules and bounded curation are an unreasonable bottleneck. Record the affected classes and estimated candidate volume first.
- Default discussion recommendation: no paid calls in the initial pass. If activated, select a provider from current official documentation and agree a bounded cost/token budget before making calls.
- Keep provider dependencies and keys outside `submission/`. The source page is untrusted data; instructions embedded in it cannot alter the extraction schema or trigger tools.
- Output draft candidates to a separate local/ignored artifact. Require schema, subject/predicate, units, bounds, dates, complete conditions and exact-source checks, then independent review, before promotion to committed derived facts.
- Do not overwrite `prose_facts.json` automatically. Record rejected candidates and the reviewed diff. Runtime needs neither the builder nor its credentials.
- An unreviewed model candidate is not a curated fact. Any new accepted extractor label must explicitly receive the same strict lint/grounding path.

**Verification:** compare each experiment on the same frozen development set, with a documented baseline and safety outcomes. A rejected experiment is a completed decision, not a reason to expand scope until it looks successful.

**Anti-pattern guards:** no unconditional model pipeline, no grading-time API calls, no judge-dependent runtime score, no adding embeddings/UI/multi-site work to compensate for missing source truth.

## Phase 6 — Independent verification and release decision

**How this serves the primary goal:** proves improvements survive independent questions and a clean public clone while preserving a known working submission if they do not.

### P4-16: Development acceptance and adversarial review

Before touching blind evaluation, freeze the candidate commit, source artifacts, route thresholds, schema, rubric and scoring versions. Require:

| Gate | Proposed criterion |
| --- | --- |
| Existing regression suite | All tests pass, including new meaningful safety and semantics tests. |
| Public/dev | At least 0.9690/1.0000; no previously perfect item regresses; zero errors and stale traps. |
| Existing generated proxy | All existing family gates pass; any score change is explained rather than silently rebaselined. |
| Source grounding | 100% of committed curated entries verify; independent review confirms subject/condition/date support for new facts. |
| Conflicts | Existing curated set stays verified and development precision/F1/resolution do not fall below the exact frozen baseline of 10/11 (displayed as 0.9091). Expanding conflict curation is not a Phase 4 prerequisite. |
| Runtime | Python 3.9/3.11; no network/SDK/query-time build; p95 <50 ms; ingest within assignment limit. |
| Packaging | Clean public-history/data/credential scan; external-kit fresh clones pass. |

Adversarial review must cover cross-product/segment aliases, unknown products, unpublished rates/programs, misleading amount/ordinal/date claims, negative wording, missing tiers, introduced/withdrawn facts, source-quality failures and complete eligibility logic. Fix development/review defects before the candidate freeze.

### P4-17: One predeclared blind comparison

- The steward evaluates the frozen `submission-v1` baseline and frozen Phase 4 candidate on the same new blind set as a paired final comparison. Register that exact pair and the frozen data/rubric/scorer in the comparison manifest before either execution; allow one run of each. Return aggregate scores, counts and uncertainty, not questions or failure examples, to implementers.
- Required proposed targets: primary family-macro semantic success at least **0.85**, positive paired improvement over baseline, description/eligibility at least **0.85** when their blind samples meet the frozen 10-cluster minimum, and no sampled family regression. Apply P4-04/P4-05's predeclared sparse-family policy: every reserved sparse blind scenario passes; development census results are reported separately as audited coverage, not independent validation. An unvalidated family cannot be claimed as generalized.
- On the audited blind set require zero unsupported confident claims, zero known stale traps, zero runtime errors and correct supporting citations/snapshots for accepted answers. Report answerable coverage and refusals separately so blanket refusal cannot appear successful.
- Aim for a material improvement (approximately ten percentage points in semantic macro success where baseline headroom permits), but do not present this as a prediction or change thresholds after results are known.
- Report clustered uncertainty and exact numerators. Positive point estimates with broad uncertainty are not proof of universal generalization.
- Existing Phase 3 holdout/locked sets may receive one final aggregate run for Phase 4 under their existing policy; no item inspection. Record their deltas and any unchanged locked weakness prominently. They are not an optimization loop or substitutes for the new source-first validation.
- If the candidate fails, retain `submission-v1` as the submission. Diagnose using development evidence or a separately planned future evaluation; do not patch and rerun the same blind set until it passes.

### P4-18: Public release and handoff

- Confirm actual implementation matches the documented APIs/schema and all proposed anti-pattern guards; review the complete diff independently.
- Clone from GitHub, fetch/check out the exact frozen candidate SHA and assert `git rev-parse HEAD` before creating a clean Python 3.11 environment. Supply kit ZIPs locally, install only runtime requirements, and run the unchanged harness and source checks. The current fresh-clone script defaults to a local committed checkout and has no `--ref`; do not mistake that for a remote-candidate check. An optional tested `--ref`/expected-SHA extension is new packaging work, not an available flag.
- Publish a new immutable grading tag only after gates pass; never move `submission-v1`. Update README, NOTES, aggregate evaluation record and submission instructions with measured results and remaining gaps.
- Record no snapshots, archives, credentials or private audit material in any public Git object. Keep provider/build artifacts out of runtime dependencies.
- Update the local email draft with the new public grading commit only if the new release is promoted. Sending the email remains a separate user action; implementation does not authorize sending it.

Existing valid verification commands (after local kit/environment setup):

```bash
python -m pytest -q
scripts/eval.sh --public --out results/phase4/public
scripts/eval.sh --dev --out results/phase4/dev
scripts/eval.sh --proxy --out results/phase4/proxy
python scripts/proxy_report.py --results results/phase4/proxy --gate
scripts/eval.sh --conflicts --out results/phase4/conflicts
python scripts/check_prose_facts.py
python scripts/check_curated.py
python scripts/bench.py --n 200
scripts/fresh_clone_check.sh --python python3.11 --snapshots-zip /path/to/participant-kit/snapshots_zip
```

Check the conflict run's precision, F1 and resolution accuracy against the frozen baseline; source verification alone does not measure those metrics. The last command validates the local committed checkout. Complete the separate exact-SHA GitHub clone procedure above for final publication.

The development JSONL can use the existing guarded harness once that file is authored:

```bash
python scripts/_guarded_run_eval.py --submission submission \
  --eval eval/generalization/dev.jsonl --out results/phase4/generalization-dev
```

New diagnostic/report/steward commands are **to be implemented**, not assumed available. Their flags must be documented and tested before they appear in runnable handoff instructions.

## Parallel execution and ownership

The implementation coordinator owns integration, acceptance decisions and shared contracts. Respect the four-agent total concurrency limit.

| Wave | Parallel work | Dependency/boundary |
| --- | --- | --- |
| 0 | Baseline/API verification; source inventory discovery | No runtime changes yet. |
| 1 | Independent dev curator; separate blind curator/steward; diagnostics implementer | Authors receive source-only context; neither gets implementation/proxy wording. |
| 2 | Coverage/quality lane; parser/routing lane; evaluation/audit tooling lane | Rubric/split frozen. Agree source-identity, semantic-annotation, date/condition-slot, trace and route contracts before concurrent edits. |
| 3 | Integrate one lane at a time; independent adversarial review | Shared `system.py`, `question.py`, `resolve.py`, registry and catalogs have one integration owner. |
| 4 | Optional experiments only for remaining diagnosed gaps | Separate branches/flags, explicit ablations and adoption decisions. |
| 5 | Candidate freeze; independent blind comparison; fresh public clone | No implementation edits based on blind feedback. |

Require each handoff to name its base commit, owned files, approved contract, tests/results, unresolved issues and whether any evaluation was run. No shared-index commits or broad `git add` while agents own different changes. Keep commits small enough to separate instrumentation, data, routing and packaging regressions.

## Approved execution decisions

Approved defaults:

1. Complete the source-first measurement and diagnosis phases before committing to retrieval or a model builder.
2. Use the 120-development/80-blind-scenario budget, with source-driven sparse-family exceptions declared before scoring.
3. Keep runtime offline and use rules plus reviewed curation first. Treat offline model spending as a separate bounded decision if the inventory justifies it.
4. Adopt a routing index/fallback only after development ablations show safe gains; leaving a rejected experiment out is acceptable.
5. Require the proposed semantic/family/safety release gates. Keep the current submission if independent validation does not demonstrate improvement.

The largest work items are independent source truth, complete semantic coverage and safe integration. A lexical ranker alone cannot repair facts the system never extracted or conditions its answer omitted.
