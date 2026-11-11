# Tier decision table

Copied from the Task 9 interfaces in `docs/superpowers/plans/2026-11-04-phase-2-facts-and-answers.md` (resolver `submission/kb/resolve.py`). `select_tier(facts, q)` dispatches on tier kind through `TIER_SELECTORS = {"balance": ..., "term": ..., "loan_amount": ..., "model_year": ..., "segment": ...}`.

| Case | Decision |
|---|---|
| bounds | inclusive bounds |
| an amount is asked | the narrowest tier containing the asked amount |
| `$100k` | means 100000 |
| `"or less"` tiers | match amounts up to the bound |
| two-digit model years | expand to the century of the lower bound |
| `7/1` | is an ARM program, never a seven-month term |
| `highest` / `lowest` | pick the max/min value among the product's tiers |
| tier unspecified | means every current tier of product+term in registry order |
| `"rate"` | on a deposit renders dividend rate and APY of the same row, on a loan rate and APR of the same row |

## Arbitration order

1. parse
2. refuse when the product is known but the attribute is not in `registry.published(product_id)` or the asked qualifier has no fact
3. exact key lookup
4. enumerate
5. else refusal

## Plan fields

- `AnswerPlan.permitted_values` = number tokens of every selected fact's `value_text`, tier bounds of selected rows, and `q.question_numbers`.
- `AnswerPlan.confident` is `False` only for refusal plans.

## Pinned examples (`tests/test_20_resolve.py`, section B)

| Question | Plan |
|---|---|
| "Can you tell me the interest rate for a 30-year mortgage?" | enumerates the tiers, 7.13 and 7.25; the stale 6.061% is not permitted |
| "What is the highest Share Savings APY?" | 0.20; the tier bound $25,000 is permitted, 0.35% is not |
| "If I keep $15,000 in Share Savings, what APY do I earn?" | 0.15 |
| "What rate would I get on a 60-month loan for a 2026 car?" | 5.39 |
| "What was the rate on the 10-month fixed jumbo special certificate as of May 2026?" with as_of 2026-05-31 | 3.90 from snapshot `02_2026-05-19_recrawl` |
| "What is your rate on a 7/1 adjustable-rate mortgage?", "What interest rate do you charge on a construction loan?", "Can you give me the lobby hours for the Mullan Avenue branch?" | refusal, `confident` False |
| "What are the APRs on the Platinum Visa and the Rewards Visa?" | `platinum_visa` then `rewards_visa`, fixed order |
