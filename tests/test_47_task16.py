from pathlib import Path
import json
from scoring import score_item
from kb.question import parse
from kb.registry import Registry
from kb.temporal import select_dated
R = Registry.load()
S01, S05 = "01_2026-05-12_baseline", "05_2026-09-28_latest"
def _facts(store, sid, attr): return store.by_product_attr[sid].get(("branch", attr), [])
def _route(q, as_of=None):
    p = parse(q, as_of, R)
    return p.intent, p.product_id, p.attribute
def _item(items, i): return next(it for it in items if it["id"] == i)
def _score(ks, it): return score_item(it, ks.answer(it["question"], it.get("as_of")))["score"]
# tests/test_26_question_gate.py (append)
def _slot(q, name): return dict(parse(q, None, R).slots).get(name)

def test_quick_win_routes():
    assert _route("what is the apy for the 17 mo special certifcate") == ("value", "cert_special", "apy") and _slot("what is the apy for the 17 mo special certifcate", "term_months") == 17  # dup-001's typo paraphrase, gap research #7
    assert _slot("Current APY on a seventeen-month share certificate special?", "term_months") == 17
    assert _slot("Rate for a thirty-year home loan?", "term_months") == 360 and _slot("Hi, can you tell me what the 30-yr mortgage rate is today?", "term_months") == 360
    assert _slot("APR on a five-year car loan for a 2025 model?", "term_months") == 60
    assert _slot("Can you give me the street address of the Galena, IL branch?", "branch_name") == "galena"
    assert _route("What's the 1st Rate APY?") == ("value", "first_rate_checking", "apy")
    assert _route("Where can I see Dupaco's certificate rates online?")[0] == _route("Which page lists share certificate rates?")[0] == "url"
    for q in ("Who can join Dupaco?", "Who qualifies for membership at Dupaco?"):
        assert _route(q) == ("value", "membership", "eligibility"), q
    assert _route("Where do I apply to join Dupaco?")[2] == _route("Can I join Dupaco online?")[2] == "url"
    assert _slot("Share savings rate for balances between 10k and 25k?", "amount") == 10000.0
    assert _slot("What is the APY on a regular 17-month certificate?", "special") is False
    assert _route("How many points on a 15-year mortgage?") == ("value", "mortgage_purchase", "points")
    assert _route("What are the mortage rates?")[1] == "mortgage_purchase"
    assert _route("Do I need $50,000 to open a High-Yield Savings account?") == ("yes_no", "high_yield_savings", "min_to_open")  # W6
    assert _route("Can I open a certificate with $500?")[2] in ("min_to_open", "min_to_earn")
    assert _route("What is the APY on a 17 month cert special?") == ("value", "cert_special", "apy") and _slot("17 mo. cert special APY?", "term_months") == 17
    assert _slot("What is the APY on a nine-month share certificate?", "term_months") == 9

def test_review_minors_m1_m2_m3():
    for raw, want in ((" 2026-05-31 ", "2026-05-31"), ("2026-05-31T10:00:00Z", "2026-05-31"), ("", None), ("   ", None), ("1900-01-01", "1900-01-01")):
        q = parse("What is the 10-month certificate special APY?", raw, R)
        assert (q.as_of, q.as_of_error) == (want, False), raw  # M1 ((pin) for " 2026-05-31 " and "1900-01-01")
    assert parse("30-year fixed rate for a $150,000 mortgage?", None, R).intent == "value"  # M2
    assert parse("Is the highest Share Savings APY 0.35%?", None, R).intent == "yes_no"  # (pin)
    assert _slot("What is the one-year certificate rate?", "term_months") == 12  # M3
    assert _slot("What's the six month CD rate?", "term_months") == 6

# tests/test_45_prose_answers.py (append)
def test_quick_win_answers(ks_full):
    from scoring import contains
    def ok(q, must, must_not=()):
        t = ks_full.answer(q).text
        assert all(contains(t, m) for m in must) and not any(contains(t, m) for m in must_not), (q, t)
    ok("what is the apy for the 17 mo special certifcate", ["4.10%"])
    ok("Current APY on a seventeen-month share certificate special?", ["4.10%"], ["3.90%"])
    ok("APR on a five-year car loan for a 2025 model?", ["5.39%"], ["5.59%"])
    ok("Can you give me the street address of the Galena, IL branch?", ["11375 Oldenburg", "61036"])
    ok("What's the 1st Rate APY?", ["2.50%"])
    ok("What changed on the 1st Rate Checking APY between May and June 2026?", ["3.00%", "2.50%"])  # (pin)
    ok("Where can I see Dupaco's certificate rates online?", ["dupaco.com/personal/savings-account"])
    ok("Where do I apply to join Dupaco?", ["join.dupaco.com"])
    ok("Share savings rate for balances between 10k and 25k?", ["0.15"], ["0.30%", "0.40%"])  # passes at 7ff32f7 by listing every tier (pin)
    ok("What is the APY on a 17 month cert special?", ["4.10%"])
    hy = ks_full.answer("Do I need $50,000 to open a High-Yield Savings account?").text  # W6: the minimum to open, not the APY
    assert "minimum to open" in hy and "APY" not in hy
    assert ks_full.answer("Can I open a certificate with $500?").text.startswith("No.")  # the minimum is $1,000.00
    assert ks_full.answer("Can I open a certificate with $1,000?").text.startswith("Yes.")  # (pin)
    assert ks_full.answer("Is a $10 deposit enough to open Bright Savings?").text.startswith("Yes.")  # $0.00 minimum
    assert ks_full.answer("What is the APY on a nine-month share certificate?").confident is False
    from kb.resolve import EARLIEST_NOTE
    early = ks_full.answer("What is the APY on the 10-month certificate special?", "1900-01-01")
    assert early.confident and "3.80%" in early.text and early.conflict_note == EARLIEST_NOTE  # (pin)
    ok("30-year fixed rate for a $150,000 mortgage?", ["7.25"], ["7.13"])  # M2: the $200,000-or-less tier, no "Yes." (pin)
    assert not ks_full.answer("30-year fixed rate for a $150,000 mortgage?").text.startswith("Yes.")
    assert ks_full.answer("What is the APY on a regular 17-month certificate?").confident is False
    heloc = ks_full.answer("What is the HELOC intro rate?", "2026-05-15").text  # gap research #8
    assert "1.99%" in heloc and heloc.endswith("will apply.")
