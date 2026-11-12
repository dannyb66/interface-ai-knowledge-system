# Phase 4 runtime contracts

These contracts describe diagnostics and reviewed claim infrastructure; reviewed corpus additions are tracked separately in [source coverage](SOURCE_COVERAGE.md). Schema validation checks structure and bounded wording; it does not prove a claim's full meaning. Independent source review remains required. This is not a personal eligibility decision engine.

Phase 4 remains unpromoted. The frozen historical v3 measurements in the [evaluation record](../EVALUATION.md) do not describe the latest working repairs. Requirements called out under integration review below still need final independent verification; their documentation is not a completion claim.

## Source identity

The organizer's `contract.Page` supplies only `url`, `title`, `markdown` and `fetched_at`. Runtime code never reads a manifest filename or filesystem path. Build-time inventories retain those identifiers separately.

`kb.source_pages.content_digest(markdown)` hashes UTF-8 text after replacing CRLF and bare CR with LF. It does not strip whitespace, normalize Unicode, or fold case. Candidate builders must decode source bytes as UTF-8 and apply this function, rather than hash raw bytes with platform-dependent newlines. This matches the text the harness supplies.

`source_page(snapshot_id, raw_url, markdown, title="", fetched_at="")` creates an immutable `SourcePage`. Its stable `page_id` hashes the snapshot ID, exact raw URL, title, fetch timestamp and content hash as a JSON array. `SourcePages` retains a deterministic canonical-URL multimap. Distinct content at one canonical URL stays distinct. Duplicate identical records collapse. Conflicting content for the same raw URL and fetch timestamp is quarantined from unpinned extraction.

`Source` adds optional `page_id`, `content_sha256` and `citation_url`. Canonical URL remains available for grouping. When a canonical group has different content, citations preserve the actual quote-bearing raw URL. Prose and conflicts verify the quote against an actual retained variant; conflict verification cannot borrow a quote from another distinct-content raw URL. Normalization is cached by content hash, never by canonical URL.

Verification filters source variants by the requested snapshot even when a caller supplies a collection containing several crawls. A source pin cannot relabel an old page as current; ambiguity checks also stay within one crawl.

## Reviewed prose version 2

Existing `_version` prose artifacts default to schema 1. Schema 1 keeps its exact field validation and rejects percentage description/eligibility quotes. Setting `_schema_version: 2` permits either unchanged version 1 entries or complete version 2 entries. Version 2 adds three required fields: `effective_date`, `semantics`, and `source_pins`. A complete entry is illustrated below; these are synthetic facts, not additions to the corpus.

```python
from dataclasses import asdict
from kb.claim_semantics import SourcePin, semantic_revision
from kb.source_pages import content_digest

sid = "05_2026-09-28_latest"
url = "https://example.test/assistance"
statement = "Applicants must have income at or below 80% of the example published limit."
pin = SourcePin(sid, url, content_digest(statement))
entry = {
    "canonical_urls": [url], "crawls": [sid], "quote": statement,
    "product_id": "mortgage_rate_relief", "attribute": "eligibility",
    "qualifiers": {}, "value": 80, "value_text": statement,
    "unit": "percent", "claim_type": "assertion",
    "published_date": None, "event_date": None, "extractor": "curated",
    "effective_date": None, "source_pins": [asdict(pin)],
    "semantics": {
        "version": 1, "claim_id": "example.threshold",
        "revision": semantic_revision(statement, statement, [pin], None),
        "role": "eligibility_condition", "comparator": "le",
        "basis": "example published limit",
        "condition_group": "example.requirements", "condition_logic": "single",
        "conditions": [statement], "numeric_unit": "percent", "scale": "",
    },
}
artifact = {"_version": "synthetic-v2", "_schema_version": 2, "facts": [entry]}
```

Every declared canonical page/crawl pair needs a pin containing `snapshot_id`, exact `raw_url`, and normalized-text `content_sha256`. The quote must occur on each pinned variant. `semantic_revision(quote, value_text, pins, effective_date)` binds the preserved statement, source pins and effective date. Candidate tools should call the helper rather than reimplement its JSON encoding. Role changes still require independent review even when the same source statement remains valid.

`Fact.semantics` is an optional immutable `ClaimSemantics`; old serialized facts restore with `None`. `fact_to_dict` and `fact_from_dict` explicitly round-trip semantic metadata and reject invalid restored units/conditions. Old unset optional source fields are omitted. Nested annotations never enter `FactKey` qualifiers.

Roles are `eligibility_condition`, `fee`, `benefit`, `organization_fact`, `procedure`, and `description`. Attribute compatibility is defined in `claim_semantics.ROLES`. Units are distinct `text`, `usd`, `count`, `percent`, `percentage_points`, and `free`. Free text does not invent a numeric zero. Percentage eligibility requires the reviewed eligibility role, a numeric threshold, comparator and preserved named basis. Percentage benefit claims cannot introduce advertised APR/APY. Unsupported compound formulas/ranges should remain full verified prose or abstain; they cannot be mislabeled as one threshold.

A percentage `description` may also be a reviewed `procedure` or `organization_fact` with exactly one primary percent value, nonempty exact basis, comparator and complete source-preserved conditions. A procedure additionally requires a named condition group. Different percentage meanings are separate claims; a mixed-percent description and advertised APR/APY remain rejected. Version 1 validation is unchanged.

Comparators are `none`, `eq`, `lt`, `le`, `gt`, and `ge`. Bound detection examines the unique primary numeric value and unit; repeated indistinguishable primary values are rejected. Inclusive and exclusive phrases are distinct. `basis`, `scale`, all declared conditions, and their connective wording must remain in the complete `value_text`. The renderer verifies the complete statement and conditions survive linting, with strict numeric grounding still enabled. Percent versus percentage-point yes/no mismatches currently refuse conservatively. A later semantic-verdict extension can produce a source-backed correction/No where logically warranted; it must not change the global legacy numeric tokenizer/scorer.

Typed eligibility yes/no requests refuse when they omit a declared condition, change a multi-condition connective, or ask for personal eligibility. Ordinary requests for the published requirements still return the complete verified statement. Typed facts using either prose or generic numeric yes/no templates state their verified rows without inventing a Yes/No verdict. Shared words do not prove a predicate, its polarity, or omitted conditions; a negative description cannot affirm its positive counterpart, and a free fee cannot affirm an arbitrary dollar amount merely because its source contains no dollar token. Version 1 verdict behavior is unchanged.

Effective dates are independent from publication, event, and fetch dates. Existing resolver date rules apply. When no `as_of` is given, semantic/fee claims effective after the chosen crawl day are excluded, including from expanded source lists. Historical and current rates retain their established resolver behavior.

## Complete prose scope and source dates

Schema 2 `claim_groups` declarations carry required IDs per entity, attribute, group and crawl. They augment the required set derived from v2 eligibility/procedure annotations before source verification. Immutable `Fact.claim_groups` survives serialization, source filtering, authority and qualifier selection. Explicit `description` declarations accept reviewed `procedure` or `description` members whose nonempty `condition_group` equals the declared claim set. All known members of that bundle augment the required set, so a declaration cannot erase a caveat or exclusion. Ordinary descriptions do not acquire requirements without an explicit declaration, and unrelated definitions or benefits are not required members. Missing or quarantined requirements remain incomplete in their own crawl; later claims cannot fill an unresolved earlier requirement. Group completeness is evaluated within its attribute. See [parsing and selection contracts](PARSING_ROUTING.md) for the exact fields and legacy ID helper.

Dated v2 prose preserves an explicit `source published on` prefix, or `event dated` when only an event date is supplied. It does not equate the publication date with the event date. This applies to procedures and narratives as well as organization statements. Every selected source statement, condition and required date prefix must survive final rendering.

Historical change and past-value rendering use the same source-date attribution. Typed equality compares the complete statement, unit, role, comparator, basis and conditions, not only a primary number. Equal claims with different publication dates remain unchanged claims while retaining both date prefixes and citations. All rendered citations are deduplicated by the exact displayed URL, snapshot and quote, so two captures of one URL remain distinct evidence.

Display cleanup recognizes only quoted Markdown block markers (`> "..."` at a line/sentence boundary) and an escaped form asterisk immediately after `(Required)`. Quoted content and the word `Required` must survive. General asterisks and comparison operators are not exempted from completeness checking. Source verification and revision hashes continue to use the original preserved wording.

## Published rate bounds

Loan `apr`/`rate` table columns explicitly headed `As Low As` retain `Fact.rate_bound: as_low_as`, independently of the numeric cell, fact key and effective date. The source quote includes the exact table header and rows. Rendering must preserve `as low as` with every selected bounded value, and bounded tables carry their own citations even at the same URL. Numeric equality and personal-rate Yes/No verdicts are suppressed for these facts. Missing header wording, other columns and deposit rates do not acquire the bound; unrelated page prose does not scope a table automatically. The optional field survives serialization and rejects unsupported bounds or missing source context.

## Scoped conflict notes

Curated conflicts may add `note_qualifiers`, a mapping of registry-approved scalar qualifier names to reviewed values. It limits answer-note applicability without changing official `Conflict` output. The reviewed regular-certificate chronology requires `term_months: 12`; the correct May-to-June history is unchanged.

An answer note requires a selected fact with matching product, attribute, every declared qualifier and a current resolution value. All evidence crawls must be no later than the selected fact's crawl and answering date. Every selected current fact is considered, and each note states its topic explicitly. Verified supporting citations join `Answer.sources`, deduplicated by exact raw URL, snapshot and quote; an earlier capture is not replaced by a current citation at the same URL. Explain and cached answers use the same note path.

One recognized entity may answer an explicitly compound eligibility-plus-service-information question. `Query.requested_prose_attributes` and `AnswerPlan.requested_prose_attributes` are frozen tuples; independent normal resolver arms retain original dates, wording and slots, and both must succeed. Output has separate eligibility and service-information labels. An incomplete arm refuses the whole request. This does not add arbitrary multi-entity or numeric compound answers, infer personal eligibility, or overwrite an explicitly unpublished attribute.

## Scalar condition slots

Implemented orthogonal scalar enums are `membership` (`member`, `non_member`), `deposit_disposition` (`deposited`, `not_deposited`), `statement_delivery` (`e_statements`, `without_e_statements`), `usage_allowance` (`within_eight_free`, `after_eight_free`), and `card` (`debit`, `credit`). An omitted condition cannot satisfy a scoped fact. Independent OR branches require only their own conditions; an AND branch requires every condition. Semantic groups alone are not selection evidence. See [conditional fee contracts](PARSING_ROUTING.md) for mandatory output labels, scoped tax companions and conservative negation handling.

Former, lapsed, expired, prospective, potential, future and hypothetical membership descriptions do not establish current membership or current nonmembership. These and equivalent uncertain/conditional wording preserve unresolved scope and refuse conditional fees rather than selecting either price branch.

Explicit membership or nonmembership in another organization also leaves Dupaco membership unresolved. Named other providers, another bank/credit union and `elsewhere` cannot select a price branch. Explicit Dupaco or the serving credit union, and ordinary current-member wording, remain positive controls; independent deposit/statement conditions are not mistaken for provider names.

## Integration requirements under review

Article publication dates or years requested as source context are source selectors, distinct from the serving `as_of` cutoff. An explicit cutoff still limits admissible evidence; selecting an older article must not silently move the serving date or permit a later source. Source attribution must preserve the selected article's publication/event meaning. Historical-source answers must not acquire a current-resolution conflict note merely because a number matches a current rate.

A historical branch bundle must satisfy every requested attribute at the applicable date; one supported attribute cannot stand in for the complete request. Planned closure or other planned-event language must remain planned rather than assert an observed event. An explicitly named unknown lab/location cannot fall through to a generic branch list or borrow a recognized sibling's evidence.

Unknown provider and unsupported amount constraints must remain explicit through parsing and resolution. Cash-advance scope must preserve the requested operation, fee/rate distinction, card class and applicable source conditions; a nearby fee or rate is not an alternative answer. These repairs are under integration review. They require fresh tests and independent development semantic verification before the latest working code can be treated as accepted.

Change queries retain the serving cutoff separately from comparison endpoints. Both an API `as_of` and an inline `as of` limit observed captures; an explicit day or month-end beyond the cutoff or available observations refuses. A bare month names a period and may select an observed capture within that month, still bounded by the cutoff. Two requested endpoints selecting the same capture cannot establish that a value stayed unchanged. This constraint concerns observations, so a source available before the cutoff may still describe a later planned event.

Bounded informational grammar may distinguish terms of office or insurance from a financial term, or an educational example from a scalar penalty. `Query.prose_reinterpreted` records that repair. It requires selected evidence to preserve the question's provider, amount and other substantive scope for both legacy and typed prose. Only explicitly introduced serving-date spans are excluded from this support comparison; the original query, numbers and cache identity remain intact. No unknown-topic recovery is enabled by this grammar.

A source-context question asking for a fraction requires a selected typed percentage claim. This is a necessary coverage check, not proof of the requested denominator or subject; the ordinary entity, source, condition and complete-group guards still apply. Missing quarantined quantitative meaning cannot be replaced by a confident grant amount or qualitative description. Reviewed numbered heading escapes are normalized identically before composition and semantic survival checks, retaining their numerals and words.

Recognition frequency and ranking position are distinct claims. An ordinal count of recognitions cannot supply a placement in a ranking; position requests require preserved typed numeric ranking evidence. Named providers, award categories and requested event years must remain supported by selected statements and their verified provenance. Source URLs can constrain category/provider scope but cannot supply a rank or count. Capture dates do not establish event years, and an explicit event year in the statement is not replaced by a later publication year. Ordinary supported frequency counts and ordinal corrections retain their existing behavior.

## Diagnostic API

`KnowledgeSystem.explain(question, as_of=None)` executes the same parser, resolver, renderer and conflict-note path as `answer`. It does not read/write the answer cache. Existing timing keys remain exactly `parse`, `resolve`, and `render`. The response retains existing fields and adds final sources/conflict note, `trace`, and ingest `source_quality` summaries.

`ResolutionTrace` is optional on parser/resolver/selection helpers. It records explicit/inferred/default/absent parser evidence; candidate identities, kept/rejected sets at the actual selection steps; and typed refusal reasons. These are observed runtime decisions, not independent truth labels. A refusal is not permission for an alternate arbitrator to bypass safety checks.

`scripts/diagnose_generalization.py --eval ... --manifest ... --rubrics ... --out ...` accepts a development-only manifest with `partition: development`, `questions_sha256` and `rubrics_sha256`, or the source curator's `phase4-dev-source-gold-v1` manifest with `artifact_sha256` entries for `dev.questions.jsonl` and `dev.rubrics.jsonl`. It verifies hashes and IDs without rewriting the frozen manifest. Sealed-looking paths are rejected before contents are opened. Detailed diagnostics go only to ignored `results/phase4` or an external local directory; stdout is aggregate only. Attributions are hypotheses requiring independent source review.

The conflict regression gate compares the exact frozen baseline `10/11`; `0.9091` is display rounding, not a stronger numeric threshold.

## Recognition scope

Ranking position, recognition frequency and the size of a recognized group are different claims. A repeat
recognition count cannot answer a ranking-position request. Explicit award-provider and event-year constraints
remain required; an article's publication date is checked as source context when requested. Ancillary history
inside a complete typed description does not acquire the award's event year. Cohort-size questions require
cohort-count evidence. The narrower occurrence-count wording checks do not apply indiscriminately to member,
employee or participant counts. Unknown provider/year/rank requests refuse; supported complete bundles keep
their source attribution and citations. Unsupported “up to/by” recognition-date wording may conservatively refuse.
