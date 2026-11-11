# Submission notes

**Entry point and dependencies.** `solution.py` exposes `build()`, returning the `ingest(snapshot)`,
`answer(question, as_of=None)` and `conflicts()` interface in the supplied `harness/contract.py`. The runtime
supports Python 3.9+; grading and primary development use Python 3.11. `requirements.txt` intentionally lists
no packages: the runtime uses the standard library only. No API keys, external services, model downloads or
live website calls are required. From the repository root, run
`python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl` after placing the supplied
kit's ZIPs in the ignored local `snapshots_zip/` directory. The public repository excludes the website snapshots
and credentials; its curated facts contain only the derived evidence needed for source verification.

**Facts and sources.** Ingestion reads only the supplied snapshots, oldest first. Rules extract rates, tiers,
contact details, dated articles and fees into a typed fact store joined to a product registry. Curated prose and
conflict entries are admitted only when their quotes and metadata verify against the listed crawl pages.
Answers cite the winning facts' sources; `conflicts()` reports the verified competing values, sources and
resolution. The system does not read evaluation labels at runtime.

**What is current and authoritative.** Without a date, the latest supplied crawl is current. An explicit
`as_of` overrides a date in the question; otherwise the newest crawl on or before the requested date applies.
Dates before the first crawl use that crawl with an explanatory note; dates after the last use the last crawl.
Malformed dates are refused. Future-effective facts are excluded. For ordinary facts, rate sheets and product
pages outrank general pages and low-authority legacy material, then effective date, publication date, fetch
time and canonical URL break ties. Dated article assertions instead choose the newest publication available
by the requested cutoff, so a later article cannot leak into a historical answer.

**Tiers and history.** The resolver retains product, segment, term, amount, model year and special/intro flags.
An asked tier selects its matching row; absent a tier, the answer lists the applicable current tiers in a fixed
order. Unsupported qualifiers do not borrow another product's value. Historical questions return evidence
available at their requested date. Change questions compare the requested endpoints or the latest supported
change; a previous-value request returns the earlier value, and unchanged or withdrawn facts have explicit
handling.

**Refusal and consistency.** Unknown products, unpublished attributes and unsupported dates, branches or
qualifiers return `confident=False` with a clear contact/refusal sentence and no new unsupported numbers.
Templates render a resolved answer plan, and numeric checks prevent unsupported values from reaching the
answer. Fixed ordering and a parsed-query cache make repeated answers deterministic. The catalog is finite:
unsupported descriptions and fees remain refusals rather than invented claims. Local measurements and their
scope are recorded in `../results/baseline.json`; the public and development scores are not an official hidden
evaluation result.
