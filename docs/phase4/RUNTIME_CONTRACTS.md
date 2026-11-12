# Phase 4 runtime contracts

These foundations add diagnostics and reviewed claim infrastructure without installing new corpus facts. Schema validation checks structure and bounded wording; it does not prove a claim's full meaning. Independent source review remains required. This is not a personal eligibility decision engine.

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

Comparators are `none`, `eq`, `lt`, `le`, `gt`, and `ge`. Bound detection examines the unique primary numeric value and unit; repeated indistinguishable primary values are rejected. Inclusive and exclusive phrases are distinct. `basis`, `scale`, all declared conditions, and their connective wording must remain in the complete `value_text`. The renderer verifies the complete statement and conditions survive linting, with strict numeric grounding still enabled. Percent versus percentage-point yes/no mismatches currently refuse conservatively. A later semantic-verdict extension can produce a source-backed correction/No where logically warranted; it must not change the global legacy numeric tokenizer/scorer.

Typed eligibility yes/no requests refuse when they omit a declared condition, change a multi-condition connective, or ask for personal eligibility. Ordinary requests for the published requirements still return the complete verified statement. Typed facts using the generic numeric yes/no template state their verified rows without inventing a Yes/No verdict; for example, a free fee cannot affirm an arbitrary dollar amount merely because its source contains no dollar token. Version 1 verdict behavior is unchanged.

Effective dates are independent from publication, event, and fetch dates. Existing resolver date rules apply. When no `as_of` is given, semantic/fee claims effective after the chosen crawl day are excluded, including from expanded source lists. Historical and current rates retain their established resolver behavior.

## Scalar condition slots for later lanes

Future conditional membership/service facts need registry-approved scalar qualifiers and matching parser/filter guards **before** corpus installation. Proposed slot names are `membership` and `service_condition`, with narrow registry enums tied to source-supported meanings. For example, a membership distinction must have explicit source wording and corresponding query evidence. An omitted query condition must not silently pick a member-only or otherwise conditional price. Ambiguous or contradictory conditions should abstain or enumerate source-supported alternatives according to the approved parser/fee plan.

These slots are an integration contract, not yet implemented here: the later lane owns exact vocabulary, registry declaration, parser evidence, selection filtering and synthetic positive/negative tests together. `condition_group` and nested conditions remain semantic metadata; a selection-relevant condition additionally needs the scalar slot. Multi-condition formulas and personal eligibility conclusions remain out of scope.

## Diagnostic API

`KnowledgeSystem.explain(question, as_of=None)` executes the same parser, resolver, renderer and conflict-note path as `answer`. It does not read/write the answer cache. Existing timing keys remain exactly `parse`, `resolve`, and `render`. The response retains existing fields and adds final sources/conflict note, `trace`, and ingest `source_quality` summaries.

`ResolutionTrace` is optional on parser/resolver/selection helpers. It records explicit/inferred/default/absent parser evidence; candidate identities, kept/rejected sets at the actual selection steps; and typed refusal reasons. These are observed runtime decisions, not independent truth labels. A refusal is not permission for an alternate arbitrator to bypass safety checks.

`scripts/diagnose_generalization.py --eval ... --manifest ... --rubrics ... --out ...` accepts a development-only manifest with `partition: development`, `questions_sha256` and `rubrics_sha256`, or the source curator's `phase4-dev-source-gold-v1` manifest with `artifact_sha256` entries for `dev.questions.jsonl` and `dev.rubrics.jsonl`. It verifies hashes and IDs without rewriting the frozen manifest. Sealed-looking paths are rejected before contents are opened. Detailed diagnostics go only to ignored `results/phase4` or an external local directory; stdout is aggregate only. Attributions are hypotheses requiring independent source review.

The conflict regression gate compares the exact frozen baseline `10/11`; `0.9091` is display rounding, not a stronger numeric threshold.
