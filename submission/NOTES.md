# Submission notes

**Interface and dependencies.** `solution.py` exposes `build()`, returning `ingest(snapshot)`,
`answer(question, as_of=None)` and `conflicts()` as defined by the supplied harness. The runtime targets
Python 3.9+; grading uses Python 3.11. `requirements.txt` intentionally lists no packages: only the standard
library is required. API keys: **none**. Runtime operation is offline, without external services, model
downloads or live website calls. [Reproduction instructions](../docs/SUBMISSION.md) explain exact-commit
checkout and supplying the participant kit separately.

**Source-backed approach.** Ingestion processes the supplied snapshots oldest first. Rules extract rates,
tiers, contact details, dated articles and fees into a typed fact store joined to a product registry. Curated
prose and conflict entries require matching source quotes and metadata. Source identity preserves the actual
crawl, raw URL and content hash, including distinct captures at a shared canonical URL. Another capture
cannot lend a quote or date. Independent source review checks meaning beyond byte matching; the runtime
does not read evaluation labels.

**Complete conditions.** Eligibility, reviewed procedures and declared description groups must retain every
required claim through source verification, selection and rendering; otherwise the complete request is
refused. Conditions preserve AND/OR logic, bounds, units, exclusions and named percentage bases. Conditional
fees retain their customer/service scope, and a tax footnote must match the fee's source and conditions.
Compound prose supports eligibility plus service information for one recognized entity only: both resolver
arms must succeed. Published conditions do not become a personal eligibility decision.

**What is current.** Without a date, the latest supplied crawl is current. Explicit `as_of` overrides a date
in the question; otherwise the newest crawl on or before the requested serving date applies. A publication
date named as source context selects evidence rather than changing the serving cutoff. Before-first dates use
the first crawl with an explanation; after-last dates use the last. Malformed dates are refused and
future-effective facts excluded. Rate sheets and product pages outrank general/legacy material, with dates,
fetch time and URL breaking ties. Dated assertions use publications available by the cutoff and preserve
publication or event attribution, so historical statements do not become current promises.

**Tiers, conflicts and grounding.** Resolution preserves product, segment, term, amount, model year and
special/intro qualifiers. Requested tiers select matching rows; otherwise applicable tiers appear in a fixed
order. Loan APR/rate cells explicitly headed “As Low As” retain that bound and table citations, without
promising an exact personal rate. Conflict notes must match the selected product, attribute, tier/conditions
and answering date, and include supporting citations. Templates render structured answer plans; numeric
grounding rejects unsupported values. Fixed ordering and full-query caching keep replay deterministic.

**Limits and release status.** The catalog is finite; unsupported requests return `confident=False` with a
clear refusal. Both `lexical_routing` and `unknown_topic_routing` remain **False**; routing experiments were
not adopted. No model builder was activated. Phase 4 remains unpromoted,
with immutable `submission-v1` as the grading fallback. [Implementation review](../docs/phase4/IMPLEMENTATION_REVIEW.md)
records experiments and pending gates; [source coverage](../docs/phase4/SOURCE_COVERAGE.md) records gaps, and
the [evaluation record](../docs/EVALUATION.md) separates historical Phase 3 results from unfinished candidate
verification. No hidden-evaluation score is claimed.
