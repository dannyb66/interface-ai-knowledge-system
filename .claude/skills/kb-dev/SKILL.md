---
name: kb-dev
description: Use when editing submission/, tests/ or scripts/ in the knowledge-hackathon repo, or when an eval item misses
---

# kb-dev

Python knowledge system under `submission/`: it answers member questions from five Dupaco website snapshots, and `harness/run_eval.py` scores it with `harness/scoring.py` (the hidden question set uses the same scorer). Add a Gotcha whenever an item misses for a new reason.

## Goals

- Maximise the hidden score: accuracy 55%, conflicts 15%, consistency 15%, speed 15%. Consistency and speed are multiplied by accuracy, so accuracy moves about 85% of the result.
- Answer numeric questions from the resolved value/tier scope; complete reviewed prose groups and explicitly requested compound prose retain every required claim and condition. Deterministic, no network, `answer()` a lookup plus a template render (target p95 under 50 ms).
- Work by weight: stale_trap, tier_disambiguation, conflict_resolution, should_refuse, list_completeness and branch_info items weigh 1.5 to 2.0 and are about 70% of the public weight.
- When an item misses, name the failing stage (extract, parse, resolve, render or refusal) with `/ask "<question>" --explain`, fix it there, and record a Gotcha if the trap is new.
- Phase4 gates run all nonsealed tests, public/dev/proxy/conflict evaluations and `scripts/fresh_clone_check.sh`; the public score must not fall below `public_final_score` in `results/baseline.json`. Real locked/holdout and new blind content remain sealed: exclude tests that read those files and retain synthetic privacy guards. Report exclusions explicitly; do not describe that result as the full suite.

## Constraints

- Harness command green; stdlib-only runtime; Python 3.9-compatible syntax; one env var (`KB_LLM_INGEST=1`, builders only); every file under 500 lines; kit files read-only (`harness/`, `eval/public_eval.jsonl`, `starter/`, `snapshots_zip/`, `snapshots/`); no commit trailers.
- A fact key is `(product_id, attribute, qualifiers)`; `qualifiers` is a sorted tuple of `(name, value)` pairs validated against `registry.QUALIFIERS`. It includes the established numeric/product qualifiers, `year`/`item`, and reviewed scalar `membership`, `deposit_disposition`, `statement_delivery` and `usage_allowance` conditions. `card` distinguishes debit/credit; brands do not imply card type. See `docs/phase4/PARSING_ROUTING.md` for the condition contract.
- Published fact attributes are exactly `apy, dividend_rate, apr, rate, points, payment_example, min_to_open, min_to_earn, fee, term_months, lobby_hours, driveup_hours, reply_hours, address, phone, routing_number, url, count, status, closure_date, eligibility, description`. Parser markers for unsupported requests, such as `cash_advance`, preserve that scope and refuse; they do not add a published fact attribute.
- Product ids come only from `submission/data/products.json`; a table row whose label the registry has never seen is ignored and counted, never guessed.
- Numeric table `value_text` is the cell after footnote stripping (`4.10%2` becomes `4.10%`); reviewed prose preserves its complete verified statement. `Source.quote` is the raw row/sentence or required exact context. Explicit `As Low As` rate bounds keep the table header and rows as evidence and remain separate immutable metadata.
- Authority classes (`submission/data/authority.json`): `rate_sheet` and `product_page` 3; `contact`, `newsroom`, `calculator`, `landing_promo`, `about` 1; `blog`, `business_resource`, `pdf`, `legacy_alias`, `listing` 0. Within a class the newest `effective_date` wins and `None` orders oldest.
- Indexes and caches are built at the end of every `ingest()`; `answer()` and `conflicts()` build nothing; the question is cut to 1,000 characters before any regex runs; `answer()` never raises.
- Read `references/as-of-contract.md` for as_of, `references/tier-decision-table.md` for tiers and arbitration, `references/formatting-contract.md` for answer text.

## Gotchas

- A frozen checkpoint is not the latest working tree. Historical v3 passed bounded regression/compatibility checks but failed independent development semantic/safety acceptance. Do not carry its results across repairs or describe its nonsealed run as the full suite; blind evaluation remains unrun until the release prerequisites pass.
- An article publication date/year in a source-context request selects evidence; it is not automatically the serving `as_of` date. Preserve both meanings and the explicit serving cutoff. A later article cannot satisfy an earlier cutoff, and an older article selector must not import current-resolution conflict notes.
- A historical branch bundle needs every requested attribute at the applicable date. Partial address/hours/status evidence is not a complete bundle. Planned closure wording does not establish that a closure happened, even when its planned date is in the past.
- A named unknown lab/location must not become a generic branch list. Another named provider, an unsupported amount or a cash-advance operation must not disappear during entity/attribute routing; retain fee-versus-rate, card and source-condition scope.
- Complete catalog facts and answered questions are different measures. Refusal triage must separate topic/selection misses from missing complete evidence; improving the former does not manufacture source support for the latter. New scope repairs remain under review until fresh integrated and independent semantic checks pass.
- Routing evidence is checkpoint-specific: the earlier six-arm ablation had no output changes, while historical v3 unknown-topic routing added one unapproved confident answer. Off/known-topic outputs were identical for its 196 development questions. Both routing flags stay off; extra confidence or token QA is not independent semantic approval.
- Shared words do not establish a typed prose predicate or its polarity. Typed yes/no answers preserve the complete evidence without automatic Yes/No; explicit negation, contractions, conditions and subject/predicate roles must not disappear behind a verdict.
- Typed temporal equality includes the full statement and conditions. Equal primary numbers do not make changed eligibility unchanged; equal statements with different publication dates retain both evidence dates. Citation identity includes URL, snapshot and quote.
- Former, lapsed, prospective or hypothetical members do not establish a current membership condition. Refuse either fee branch when current membership is unresolved.
- A loan table's `As Low As` column header is part of its rate claim. Retain its explicit bound and header evidence through extraction/serialization/rendering, and never infer an exact or personal-rate Yes verdict from that minimum. Do not extend the bound to other columns or fixed deposit rates.
- Equal numeric values do not establish conflict-note scope. Match reviewed qualifiers, bound every evidence crawl by the answer date, label the note's topic, and retain its historical URL/snapshot/quote citations.
- In a compound request, a recognized entity in one clause cannot lend evidence to an unknown subject in another clause. Refuse unresolved subjects before producing either partial answer.
- A condition word inside unknown or unrecognized negative wording is not affirmative evidence. Scope fee branches before selection; known negatives must not negate neighboring conditions, and `without e-statements` needs its explicit charged branch.
- Missing retrieval coverage cannot establish website absence or product discontinuation. Generic refusals say what the system cannot confirm; historical rate identity does not prove an offer ended.
- Any `must_not_include` token zeroes the item, even inside "was X, now Y" or "not X": one resolved fact per answer, never a list of candidates, no superseded value, no sibling tier or product.
- A refusal is `confident=False` plus a `REFUSAL_RE` phrase (`I can't confirm`, `isn't listed`, `please contact`) and no digit absent from the question. The scorer accepts either the flag or the phrase; ship both.
- `doesn't list` alone is NOT a `REFUSAL_RE` phrase. `I can't confirm` is, but only with the leading "I" and a straight apostrophe: `We can't confirm` and a curly U+2019 apostrophe fail. `I couldn't find`, `not published` and `contact us` fail too.
- A phone number or date in a refusal fails it: `Please call 800-373-7600` adds digits the question lacks.
- The three public refusals have no grounded value in any snapshot, by design: the 7/1 ARM rate, the construction-loan rate and the Mullan Avenue branch hours. Refuse each digit-free; numbers already in the question, such as the 7 and 1 of "7/1", are allowed.
- Numbers carry units and match by value and unit: `5.39% APR`, never `5.39 APR` (it fails a `5.39%` token); dollar amounts keep the `$` sign and comma thousands (`\$1,000`; the backslash is deliberate, so Claude Code does not treat the figure as an argument placeholder). A unitless token matches any unit, and `22` does not match `22,000`.
- Tokens keep the site's surface form: `8 a.m.` (not `8am` or `8:00 a.m.`), `273974581` (no hyphens, no masking), `March 31, 2026` (not `2026-03-31`), phone `800-373-7600` (not `(800) 373-7600`). A token with a colon such as `8:30` is matched as text.
- Dates, times and phone numbers shed integers into the answer's number set, which the consistency pillar compares across paraphrases and repeats (`March 31, 2026` adds 31 and 2026, `8 a.m.-6 p.m.` adds 8 and 6). Avoid incidental metadata in numeric answers, but never drop source-date attribution or conditions required by reviewed prose; include their verified metadata in numeric grounding.
- Never emit these text traps: `in these facts`, `ZIP code`, `unable to find`, `don't have that detail`, `Which certificate term would you like`, `***`, `<val`, `Jump Start`, `24 branch`, `up to 0.35`, stale URLs on `info.dupaco.com` or `/locations/branch-hours`. Never ask a clarifying question on a list or branch item.
- A URL question needs the full URL in the answer text; `sources` alone do not satisfy `must_include`. Source credit compares lowercased `host/path` keys (scheme, `www.`, query, fragment and trailing slash are ignored): cite `https://www.dupaco.com/...` pages, never a double slash; a wrong sub-path earns nothing.
- Rendered text never contains `{`, `<`, `*` or `\r\n`, and a non-refusal answer holds only permitted numbers (selected values, tier bounds, numbers in the question); the stray-number lint enforces both.
- Speed is the p95 of all answers: no lazy work on the first call (build indexes in `ingest()`), no LLM or network in `answer()`; an exception or a call over 60 s scores 0.
- Use an explicit sort key wherever a winner is chosen, never dict, set or input order: the same fact must give the same number set for every paraphrase and repeat, under any hash seed.
- Python 3.9-compatible syntax in `submission/`: no `match`, no `X | Y` types evaluated at runtime, no `zip(strict=)`, no `dataclass(slots=True)`.
- No network call and no SDK import (`anthropic`, `openai`) under `submission/`: stdlib only, and `os.environ` is read only in `kb/config.py`.
- The snapshots are a real credit union's public website, shared for this event only. They are private: never redistribute them or paste page text into tracked docs, agent memory or PR text.
- Items with an empty `must_include` outside `should_refuse` score 0 without `--judge` whatever you answer: avoid their trap phrase and do not chase them.

## Commands

- `/eval [--public|--dev|--locked|--quick]` runs `scripts/eval.sh`: the harness plus a table of misses. With `--locked` read the aggregate score only.
- `/ask "<question>" [--as-of D] [--explain]` runs `python scripts/ask.py`: the answer, its confidence and sources, and with `--explain` the winning fact.
- `/bench [--n N]` runs `python scripts/bench.py`: p50 and p95 per stage.
- `/fresh-clone` runs `scripts/fresh_clone_check.sh`: a clean venv and the public eval under the socket guard, on committed state only.
- `/go` runs pytest, `scripts/eval.sh --quick` and `/simplify`, then commits and opens a PR.
- Checks: `python -m pytest -q` and `python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl`.
- Wrappers that work from any directory: `.claude/skills/kb-dev/scripts/eval.sh`, `ask.sh` and `bench.sh`.
- Agents: `eval-analyst` after every eval run, `adversarial-reviewer` before each merge, `fact-auditor` for audit-sheet slices, `grader-sim` for a fresh clone in a worktree.
