# Phase 4 parsing and conditional selection

This lane implements hard fee scope, complete eligibility/procedure groups, bounded compound prose answers, and an opt-in source-derived route experiment. Corpus additions require their separate source audit. The original six-arm ablation produced no answer changes; later unknown-topic routing added one unadopted answer. An isolated source-context variant produced no recovery attributable to its new mechanism and was rejected. Both production route flags remain disabled. Historical checkpoint results below do not certify subsequent working changes.

## Conditional fees

Registry rules and reviewed prose accept these scalar qualifiers:

| Qualifier | Values |
| --- | --- |
| `membership` | `member`, `non_member` |
| `deposit_disposition` | `deposited`, `not_deposited` |
| `statement_delivery` | `e_statements`, `without_e_statements` |
| `usage_allowance` | `within_eight_free`, `after_eight_free` |
| `card` | `debit`, `credit` |

The parser reads explicit conditions, including supported negative wording. Contradictory or unrecognized negation cannot select an affirmative price condition. Visa alone is a brand, not a credit-card classification. A fact carrying a qualifier requires that exact query value; omitted conditions do not satisfy a conditional price. Separate OR branches are independently sufficient: a nonmember branch need not know deposit disposition, while a free member-and-deposited branch requires both.

The numeric fee extractor derives narrow conditions from its own schedule wording for nonmembers, e-statements and the eight-free allowance. Scope words appear in the final fee label, and post-render validation requires them to survive.

Branch-specific `value_text` can be an exact source substring while the full quote retains schedule context. A free coin branch uses `Free for members`, both member/deposited qualifiers, and an explicit deposited condition in its rendered label. It does not acquire the charged branch's tax caveat. These interpretations require independent source review; structural validation alone does not prove the truth table.

A numeric fee's source asterisk may render without that marker only when its scoped tax companion survives. Matching requires the same product, condition group, crawl, canonical page, verified content hash and scalar conditions. Another raw capture cannot lend a footnote. A tax-only fragment cannot answer a price question. General numeric lint and quote verification remain unchanged.

At ingestion, an exact duplicate legacy fee is removed when a verified v2 curated fact has the same key, effective date, value/unit, snapshot, raw URL and content hash, with overlapping source-row quotes. Disagreeing values, scopes, dates, pages and unrelated rows remain. This prevents a numeric-only duplicate from outranking its complete reviewed fee; temporal and authority ranking are unchanged.

## Complete eligibility and procedures

Schema 2 supports optional top-level `claim_groups`, a list of objects with exactly `entity`, `attribute`, `claim_set`, `crawls`, and `required_claim_ids`. The attribute is `eligibility`, or `description` for reviewed procedure/description bundles; IDs and crawls are strings/lists of strings. For example:

```json
{"entity": "example_program", "attribute": "eligibility",
 "claim_set": "example_program.requirements", "crawls": ["example_snapshot"],
 "required_claim_ids": ["example.residency", "example.deposit"]}
```

`kb.claim_groups.claim_identity(entry)` uses the semantic claim ID for v2 and the existing stable `legacy:` hash for v1. V2 groups derive required IDs before source verification; reviewed declarations add requirements and cannot remove derived members. A declared missing or quarantined requirement intentionally blocks complete eligibility. Declarations must match an existing entity/attribute/crawl.

Immutable `Fact.claim_groups` carries identity and required membership through serialization and selection. Ingestion binds catalog requirements to every extractor's matching entity/attribute/crawl, so an unannotated higher-authority alternative cannot bypass completeness. Source loss or loss during authority/qualifier selection makes complete requirements refuse. Explicit description bundles require matching nonempty semantic `condition_group` values and reviewed `description` or `procedure` roles; all annotated members augment the declared required IDs. Missing/quarantined source requirements remain incomplete in that crawl. Benefits are not merged into eligibility groups. Renewal, rollover and other subscopes need distinct source-backed entities or remain quarantined.

Reviewed `procedure` descriptions may preserve a single typed percent value with exact basis, comparator, complete source conditions and a named condition group. An organization statement may use the same bounded percent contract when appropriate. This does not allow untyped percentage text, mixed primary percentages, or advertised APR/APY. Distinct procedural branches remain separate claims and both required IDs must survive. An additional definition can share the entity/description scope without becoming a required procedure member. Required membership is stable per crawl; a temporal change that cannot be represented honestly remains quarantined.

Every dated v2 prose fact carries explicit source-publication attribution, or explicit event-date attribution when no publication date exists. This applies to historical narratives and procedures as well as organization facts. The actual source wording retains any distinct event year. Date tokens enter strict numeric grounding from the reviewed metadata, and post-render validation requires the attribution to survive. How-to prose uses the same attributed renderer.

## Bounded compound prose

`Query.requested_prose_attributes` is an immutable tuple for a single recognized entity explicitly asked about both eligibility and service information. General request grammar detects membership/eligibility plus delivery, operation, features or licensing; an unrecognized coordinated product phrase cannot be erased. Explicit financial attributes, arbitrary multiple entities and personal eligibility decisions remain outside this path.

The resolver runs the normal arbitration separately for `eligibility` and `description`, keeping the original wording, dates, numbers and slots. Both arms must publish the attribute and produce complete supported plans in the same crawl. Missing source, date exclusion, authority loss or an incomplete required group makes the entire request refuse. The bounded grammar permits the recognized entity's aliases and ordinary request/reference words; an unknown subject or modifier, including after `and what services does ...`, sets `Query.prose_scope_error` and refuses before either arm or optional routing. Successful output labels eligibility separately from service information, so an agency's licensing locations are not recast as customer requirements. It states verified evidence without a Yes/No eligibility verdict. Final rendering must retain both labels and every selected statement. The full original Query, including requested attributes and scope errors, remains the cache key; explain follows the same path.

## Route experiment

Construction options are `Config.from_env(lexical_routing=True, unknown_topic_routing=False, routing_min_score=0.6, routing_min_margin=0.2)`. Both booleans default to `False`; no environment variable selects a grading path. Unknown-topic routing also requires lexical routing. Catalog ablations should use isolated runtime copies: existing `Config.data_dir` does not replace all registry/label lookups.

`LexicalIndex.build(store, registry)` runs after ingestion. Its generation hash covers source-derived targets, aliases, vocabulary and provenance; evaluation questions are never inputs. Targets collapse to entity/attribute scopes before ambiguity comparison. Tokens are lowercase words with a fixed stop list and conservative suffix normalization. Scores are inverse-frequency-weighted query-token overlap, not confidence. Document frequencies are precomputed. Candidate scopes must exist in the latest crawl; the normal resolver still determines dates, authority, tiers and final facts.

Recovery preserves unambiguous direct routes. It excludes hard tier/program slots, malformed dates, historical/multi-entity/compound requests, question numbers, unsupported fee operations and yes/no claims. An absent date or an `as_of` exactly equal to the serving crawl day is eligible; all other dates remain blocked. Recognized-entity recovery repairs a missing attribute or an inferred rate default when general informational grammar supports that transition. An explicit attribute is never overridden. Unknown-entity recovery may preserve an explicitly requested prose attribute only when the candidate publishes that same attribute.

The separate unknown-topic experiment restricts candidates to the `information` family, requires two source-alias token anchors, the frozen overlap/margin and no novel modifiers outside target vocabulary or a small question-grammar vocabulary. Unknown provider/product modifiers abstain. This intentionally does not discover every business-service or education entity.

`apply_route` preserves original wording, numbers and explicit slots, updates entity/attribute/key and clears derived generic-rate state. It never reparses generated text. `answer()` caches under the original complete `Query`; `explain()` uses the same recovery and resolver without cache mutation. Queries never build the lexical index or read artifact files.

Broad grammar repairs recognize purpose wording without defaulting to a rate, distinguish addressing a problem from asking a postal address, preserve `routine` as an ordinary word, and distinguish checking as an action from a checking account. Named program eligibility outranks incidental employee-count words. Lost-device procedures do not borrow the general phone number; member-story wording does not borrow a generic current financial product. Explicit unpublished financial attributes retain refusal behavior.

## Validation and remaining release gates

Tests cover source/selection loss, serde, extractor bypass, OR branches, negative/unknown conditions, card class, scoped footnotes, raw-variant collisions, duplicate-shadow boundaries, route ties, hard refusals, original-query caching and no query-time index/file access.

The historical frozen six-arm experiment crossed old/new catalogs with routing disabled, known-entity recovery, and unknown-topic recovery. Runtime/data/question/rubric/harness hashes were retained locally; runtime copies were isolated. Within each catalog, all three configurations produced identical answers and citations. The old catalog scored 0.0493 QA / 0.0485 final; the then-new catalog scored 0.1084 QA / 0.1063 final on the 196-item development set. All arms had zero harness errors and raw traps. These were token-scoring diagnostics, not semantic scores or measurements of the final catalog. No threshold was relaxed to increase coverage.

Later expanded-catalog comparisons produced one additional confident answer only with unknown-topic routing. On frozen historical v3, off and known-topic outputs matched on all 196 development questions. The extra answer was not independently approved or adopted; both route flags stayed off.

The isolated source-context-v1 experiment used separate runtime copies. Its disabled output matched frozen v5 exactly; its enabled output changed only that same pre-existing unknown-topic answer. The new source-context normalization did not run for that changed answer, so its causally attributable recovery count was **zero**. The variant was rejected and was not integrated. Mechanical controls do not establish semantic acceptance, and the experiment did not justify broader normalization or relaxed guards.

Earlier lane checks passed 75 focused and 30 parser tests; their 118-test compatibility run exposed a stale catalog-shape expectation that was subsequently reconciled. That issue is no longer an open handoff item. The last verified checkpoint, historical v5, passed 979 nonsealed tests, with two sealed-data reader tests deselected and the holdout module excluded. Its public/original-dev scores were 0.9690/1.0000, and proxy 0.9976 passed all family gates. Its independent development result was 45/196 questions, 16/98 scenarios and primary macro 0.155556, with one unsupported confident claim also causing one citation and one temporal failure. See the [evaluation record](../EVALUATION.md) for checkpoint scope and performance.

v5 is not the latest working tree or an accepted grading commit. A recognition category/year attribution repair is under review; final integrated verification, the blind decision and exact-SHA GitHub reproduction remain pending. No blind evaluation was used by this lane. Source curation is closed, all routing flags remain off, and no model builder was activated.
