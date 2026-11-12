# Reviewed source coverage

Source coverage and answer quality measure different things. The historical
41/44 metric counted products with either a description or any eligibility
statement. The new matrix keeps that denominator separate and records entity,
attribute, complete required claim set, and crawl. Presence of one condition does
not establish complete eligibility. Matrix totals apply only to reviewed source
requirements, not to every claim on the website or to unseen questions.

`scripts/phase4_sources.py` loads original manifest records into a canonical-URL
multimap. Exact raw URLs, actual crawl identity, and newline-normalized content
hashes remain distinct. The candidate builder expands a reviewed statement over
all matching source variants; it never consults evaluation files or calls an API.
Every generated v2 entry binds its quote, value text, source pins, and effective
date to a semantic revision. Semantic annotations, including conditions and
roles, are bound by the independently reviewed whole-catalog hash. An independent
source review is required before adding candidates to the submission.

For dated v2 claims, the omitted-source census concerns the same publication
context. Publication is checked against each actual pinned source. An identical
generic sentence from another date is not silently treated as the same program.
Independent review must also establish the subject and predicate of every source;
matching dates alone never establish that relationship. Legacy v1 census behavior
is unchanged. Rebuilding an existing dated v2 artifact preserves its reviewed
publication scope. Newly supplied seed statements can request a reviewed date
scope with the build-time-only `_publication_scope` field.

The validator separately checks all exact pins, omitted raw aliases, actual
publication dates, and fee effective dates. A correct quote on another raw page
cannot rescue a changed or absent pin. Required eligibility groups are established
before source verification, so dropping one condition cannot make the remaining
subset appear complete. Reviewed procedure groups and explicit description bundles
use the same survival rule. The builder preserves these groups during replay.
Required members keep their truthful semantic role; a condition is never relabeled
as a benefit or a procedure to bypass validation.

Quality decisions deliberately distinguish malformed organization counters such
as `NaN` or rendered `Members 0+` from legitimate free or zero-price services.
Conditional fees retain their customer and service scope. Percentage thresholds
keep the exact published basis; percentage points remain a different unit.
Mixed-unit benefits with incomplete qualification context are quarantined until
their full meaning can be represented. Conflicting application-cycle dates do
not become a current eligibility assertion. Educational statements retain their
specific topic and do not become an inferred personal eligibility decision.

The initial expansion leaves 24 historical fee branch/crawl combinations without
a complete admitted curated row. Some older variants contain encoded table text;
finding their tax footnote alone is insufficient. These remain explicit coverage
gaps. The standalone Mortgage Rate Relief benefit is also quarantined because
its mixed-unit qualification context cannot yet be represented completely.

The second bounded curation pass covers source subjects such as PMI removal,
payment-app balance advice, dated organization reports, and source-described
procedures. Procedure membership is checked for each crawl. A wording-only change
uses an exact historical variant under the same stable claim ID. A genuinely
later source statement is not projected backward. Where an older advisor guide
has blank infographic text, the complete historical checklist remains unavailable
rather than presenting its surviving subset as complete.

Dated prose carries its actual source-publication or event attribution. A historical
award, a member's story, or an educational example is not recast as a current
organization count, product promise, or price. The PMI procedures preserve the
source's distinct 20% equity/appraisal and 78% balance/request-without-appraisal
branches; neither branch introduces a legal automatic-termination rule. The
typed percentage contract still rejects arbitrary untyped percentages, mixed
percentage meanings, APR, and APY in prose.

Known exclusions include the advisor's approximate AUM benchmark, the curbstoning
risk statistic, mixed-rate Credit Coach prose, and mixed-percentage Habitat
comparisons. Source agreement and corpus coverage do not by themselves establish
answer quality; development and final semantic review remain separate gates.

The independently reviewed installed catalog has 397 entries, including 290 v2
claim identities. Validation checks 1,794 entry/page/crawl pairs and 1,602 exact
raw-source pins. The local reviewed-requirements matrix has 654 complete rows out
of 680: the remaining rows are 24 historical fee scopes and two older advisor
scopes whose image content is unknown. Legacy product descriptions remain 44/44.
These are source-coverage counts, not answer scores or an unseen-evaluation result.

Recheck the installed catalog with:

```sh
python scripts/check_prose_facts.py
python scripts/build_reviewed_candidates.py \
  --seeds submission/data/prose_facts.json \
  --products submission/data/products.json \
  --out results/phase4/rebuilt-prose.json
```

The source steward's local requirements manifest can be inspected with:

```sh
python scripts/source_coverage_report.py \
  --requirements <reviewed-requirements.json> \
  --audit <independent-hash-attestation.json> \
  --out results/phase4/coverage-report
```

Without an independent attestation bound to the exact requirements, catalog,
and registry hashes, that report explicitly remains provisional. Full source
pages, local review extracts, and evaluation artifacts remain outside Git.
