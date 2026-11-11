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
# tests/test_46_change.py (append)
def test_change_points_print_the_last_change(ks_full):  # gap research #2
    t = ks_full.answer("When did the 17-month certificate special APY change?").text
    assert all(s in t for s in ("3.95%", "4.10%", "August 27, 2026", "September 28, 2026")) and "3.85%" not in t
    t = ks_full.answer("When was the last change to the 30-year fixed mortgage rate for loans of $100,000 or less?").text
    assert "6.375" in t and "7.13" in t and "5.875" not in t

def test_withdrawn_products_are_no_longer_offered(ks_full):  # gap research #3
    from scoring import REFUSAL_RE, _numbers
    for q in ("What is the APY on the 25-month certificate special?", "What is the HELOC intro rate?"):
        a = ks_full.answer(q)
        assert a.confident is False and "no longer offered" in a.text and REFUSAL_RE.search(a.text), q
        assert _numbers(a.text) <= _numbers(q), q  # no digit absent from the question
    assert "3.60%" in ks_full.answer("What APY did the 25-month certificate special pay in May 2026?").text  # dev-006: inside the window (pin)
    assert "1.99%" in ks_full.answer("What is the HELOC intro rate?", "2026-05-15").text  # (pin)

# tests/test_26_question_gate.py (append)
def test_change_point_questions():
    for q in ("When did the 17-month certificate special APY change?",
              "When was the last change to the 30-year fixed mortgage rate for loans of $100,000 or less?"):
        p = parse(q, None, R)
        assert (p.intent, p.change_point, p.as_of) == ("change", True, None), q
    assert parse("How did the 36-month personal loan APR change between May and June 2026?", None, R).change_point is False
