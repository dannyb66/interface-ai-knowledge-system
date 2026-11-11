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
def test_mentions_bind_their_own_qualifiers():
    p = parse("What are the APYs on the 17-month certificate special and the 10-month jumbo certificate special?", None, R)
    assert [dict(m)["term_months"] for m in p.mentions] == [17, 10] and [dict(m).get("jumbo") for m in p.mentions] == [None, True]
    assert [dict(m)["term_months"] for m in parse("What are the 30-year and 15-year mortgage rates?", None, R).mentions] == [360, 180]
    assert [(dict(m)["product_id"], dict(m)["term_months"]) for m in parse("What are the 60- and 72-month auto loan rates for a 2026 car?", None, R).mentions] == [("auto_loan", 60), ("auto_loan", 72)]
    p = parse("Compare the 36-month personal loan APR with the 60-month auto loan APR for a 2026 car.", None, R)
    assert [(dict(m)["product_id"], dict(m)["term_months"]) for m in p.mentions] == [("personal_loan", 36), ("auto_loan", 60)]
    assert parse("What's the HELOC rate and the 15-year fixed mortgage rate?", None, R).generic_rate is True
    assert parse("What is the 17-month certificate special APY?", None, R).mentions == ()
    assert [dict(m)["term_months"] for m in parse("Which pays more, the 10- or 17-month special?", None, R).mentions] == [10, 17]

# tests/test_45_prose_answers.py (append)
def test_mentions_answer_each_mention(ks_full):
    from scoring import contains
    def ok(q, must, must_not=()):
        t = ks_full.answer(q).text
        assert all(contains(t, m) for m in must) and not any(contains(t, m) for m in must_not), (q, t)
    ok("What are the APYs on the 17-month certificate special and the 10-month jumbo certificate special?", ["4.10%", "4.00%"], ["4.20%"])
    ok("What are the APYs on the 10-month jumbo certificate special and the 17-month certificate special?", ["4.10%", "4.00%"], ["4.20%"])
    ok("What are the 30-year and 15-year mortgage rates?", ["7.13", "6.75"])
    ok("What are the 60- and 72-month auto loan rates for a 2026 car?", ["5.39%", "5.49%"], ["5.59%"])
    ok("Compare the 36-month personal loan APR with the 60-month auto loan APR for a 2026 car.", ["10.49%", "5.39%"])
    ok("What's the HELOC rate and the 15-year fixed mortgage rate?", ["6.25%", "6.75"])

def test_comparison_verdict(ks_full):  # gap research #9
    lines = ks_full.answer("Which pays more, the 10- or 17-month special?").text.splitlines()
    assert any("3.90%" in l for l in lines) and any("4.10%" in l for l in lines)
    assert lines[-1] == "The second one is higher." and not any(ch.isdigit() for ch in lines[-1])
