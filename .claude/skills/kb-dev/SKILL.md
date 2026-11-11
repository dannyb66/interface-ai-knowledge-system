---
name: kb-dev
description: Use when editing submission/, tests/ or scripts/ in the knowledge-hackathon repo, or when an eval item misses
---

# kb-dev

Python knowledge system under `submission/`: it answers member questions from five Dupaco website snapshots, and `harness/run_eval.py` scores it with `harness/scoring.py` (the hidden question set uses the same scorer). Add a Gotcha whenever an item misses for a new reason.

## Goals

- Maximise the hidden score: accuracy 55%, conflicts 15%, consistency 15%, speed 15%. Consistency and speed are multiplied by accuracy, so accuracy moves about 85% of the result.
- Answer each question from ONE resolved fact: deterministic, no network, `answer()` a lookup plus a template render (target p95 under 50 ms).
- Work by weight: stale_trap, tier_disambiguation, conflict_resolution, should_refuse, list_completeness and branch_info items weigh 1.5 to 2.0 and are about 70% of the public weight.
- When an item misses, name the failing stage (extract, parse, resolve, render or refusal) with `/ask "<question>" --explain`, fix it there, and record a Gotcha if the trap is new.
- Every gate runs pytest, the public eval, the dev items, the locked set and `scripts/fresh_clone_check.sh`; the public score must not fall below `public_final_score` in `results/baseline.json`.

## Constraints

- Harness command green; stdlib-only runtime; Python 3.9-compatible syntax; one env var (`KB_LLM_INGEST=1`, builders only); every file under 500 lines; kit files read-only (`harness/`, `eval/public_eval.jsonl`, `starter/`, `snapshots_zip/`, `snapshots/`); no commit trailers.
- A fact key is `(product_id, attribute, qualifiers)`; `qualifiers` is a sorted tuple of `(name, value)` pairs whose names are exactly `term_months, jumbo, special, balance_min, balance_max, loan_amount_max, model_year_min, model_year_max, program, card, segment, branch_name, day, intro`.
- Attribute names are exactly `apy, dividend_rate, apr, rate, points, payment_example, min_to_open, min_to_earn, fee, term_months, lobby_hours, driveup_hours, reply_hours, address, phone, routing_number, url, count, status, closure_date, eligibility, description`.
- Product ids come only from `submission/data/products.json`; a table row whose label the registry has never seen is ignored and counted, never guessed.
- `value_text` is the cell after footnote stripping (`4.10%2` becomes `4.10%`); `Source.quote` is the raw table row or sentence.
- Authority classes (`submission/data/authority.json`): `rate_sheet` and `product_page` 3; `contact`, `newsroom`, `calculator`, `landing_promo`, `about` 1; `blog`, `business_resource`, `pdf`, `legacy_alias`, `listing` 0. Within a class the newest `effective_date` wins and `None` orders oldest.
- Indexes and caches are built at the end of every `ingest()`; `answer()` and `conflicts()` build nothing; the question is cut to 1,000 characters before any regex runs; `answer()` never raises.
- Read `references/as-of-contract.md` for as_of, `references/tier-decision-table.md` for tiers and arbitration, `references/formatting-contract.md` for answer text.

## Gotchas

- Any `must_not_include` token zeroes the item, even inside "was X, now Y" or "not X": one resolved fact per answer, never a list of candidates, no superseded value, no sibling tier or product.
- A refusal is `confident=False` plus a `REFUSAL_RE` phrase (`I can't confirm`, `isn't listed`, `please contact`) and no digit absent from the question. The scorer accepts either the flag or the phrase; ship both.
- `doesn't list` alone is NOT a `REFUSAL_RE` phrase. `I can't confirm` is, but only with the leading "I" and a straight apostrophe: `We can't confirm` and a curly U+2019 apostrophe fail. `I couldn't find`, `not published` and `contact us` fail too.
- A phone number or date in a refusal fails it: `Please call 800-373-7600` adds digits the question lacks.
- The three public refusals have no grounded value in any snapshot, by design: the 7/1 ARM rate, the construction-loan rate and the Mullan Avenue branch hours. Refuse each digit-free; numbers already in the question, such as the 7 and 1 of "7/1", are allowed.
- Numbers carry units and match by value and unit: `5.39% APR`, never `5.39 APR` (it fails a `5.39%` token); dollar amounts keep the `$` sign and comma thousands (`\$1,000`; the backslash is deliberate, so Claude Code does not treat the figure as an argument placeholder). A unitless token matches any unit, and `22` does not match `22,000`.
- Tokens keep the site's surface form: `8 a.m.` (not `8am` or `8:00 a.m.`), `273974581` (no hyphens, no masking), `March 31, 2026` (not `2026-03-31`), phone `800-373-7600` (not `(800) 373-7600`). A token with a colon such as `8:30` is matched as text.
- Dates, times and phone numbers shed integers into the answer's number set, which the consistency pillar compares across paraphrases and repeats (`March 31, 2026` adds 31 and 2026, `8 a.m.-6 p.m.` adds 8 and 6). Leave out effective dates, years and phone numbers unless the question asks for them.
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
