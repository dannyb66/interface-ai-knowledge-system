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
# tests/test_45_prose_answers.py (append)
def test_list_guard_and_family_words(ks_full, public_items, store_full):
    from kb.question import parse
    from kb.registry import Registry
    from kb.resolve import resolve
    R = Registry.load()
    p = resolve(parse("What are the APYs on Bright Savings and Launchpad Savings?", None, R), store_full, R)
    assert [f.product_id for f in p.facts if f.attribute == "apy"] and {f.product_id for f in p.facts} == {"bright_savings", "launchpad_savings"}
    t = ks_full.answer("What are the APYs on Bright Savings and Launchpad Savings?").text
    assert "2.25%" in t and "3.25%" in t and "Share Savings" not in t
    for i in ("dup-034", "dup-040"):
        assert _score(ks_full, _item(public_items, i)) == 1.0
    p = resolve(parse("What are the rates on credit cards and auto loans?", None, R), store_full, R)
    assert {"platinum_visa", "rewards_visa", "auto_loan"} <= {f.product_id for f in p.facts}
    assert "4.20%" in ks_full.answer("What is the highest CD rate?").text  # cert_special / ira_cert 17-month jumbo @05
    # M8: the family maximum @05 is Launchpad Savings 3.25% ($5-$1,000); High-Yield's top tier is 2.45%
    t = ks_full.answer("Which savings account has the highest APY?").text
    assert "3.25%" in t and "0.20%" not in t
    p = resolve(parse("What savings accounts do you offer and what are their APYs?", None, R), store_full, R)
    assert {f.product_id for f in p.facts} == {"share_savings", "bright_savings", "high_yield_savings", "holiday_club_savings",
                                               "you_name_it_savings", "launchpad_savings"}
    t = ks_full.answer("What savings accounts do you offer and what are their APYs?").text
    assert "0.35%" not in t and "0.30%" not in t
    loans = ks_full.answer("What are all of your loan rates?")
    assert loans.confident and loans.text.startswith("Lowest current rate for each loan:")
    assert all(n in loans.text for n in ("Auto Loan", "Personal Loan", "Home Loans - Purchase", "Home Equity Line of Credit"))
    pair = resolve(parse("What are the APRs on the 36-month personal loan and the 60-month auto loan for a 2026 car?", None, R), store_full, R)
    assert {f.product_id for f in pair.facts} == {"personal_loan", "auto_loan"}  # no boat/RV or ATV rows (adversarial note)

def test_family_superlative_never_trips_share_savings_traps(ks_full, public_items):  # (pin) gap research §1
    for i, token in (("dup-046", "0.35%"), ("dup-049", "up to 0.35")):
        it = _item(public_items, i)
        assert _score(ks_full, it) == 1.0 and token not in ks_full.answer(it["question"]).text, i
