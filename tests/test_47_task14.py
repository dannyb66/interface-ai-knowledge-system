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
def test_change_end_dates_parse():
    p = parse("How did the 30-year fixed mortgage rate for loans of $100,000 or less change between June and August 2026?", None, R)
    assert (p.intent, p.as_of, p.as_of_end) == ("change", "2026-06-30", "2026-08-31")
    p = parse("What happened to the 30-year mortgage rate for loans of $100,000 or less between the June and August 2026 crawls?", None, R)
    assert (p.intent, p.as_of, p.as_of_end) == ("change", "2026-06-30", "2026-08-31")
    p = parse("What happened to the 30-year mortgage rate between the June and August crawls?", None, R, reference_date="2026-09-28")
    assert (p.intent, p.as_of, p.as_of_end) == ("change", "2026-06-30", "2026-08-31")  # reference_date: Optional[str], as C1 merged it
    p = parse("Has the 36-month personal loan APR changed since May 2026?", None, R)
    assert (p.as_of, p.as_of_end) == ("2026-05-31", None)

# tests/test_46_change.py
from scoring import contains

def _has(text, must, must_not):
    return all(contains(text, t) for t in must) and not any(contains(text, t) for t in must_not)

def test_change_between_intermediate_crawls(ks_full):
    cases = [
        ("How did the 30-year fixed mortgage rate for loans of $100,000 or less change between June and August 2026?", ["6.125", "6.375"], ["7.13"]),
        ("How did the 30-year fixed mortgage rate for loans of $100,000 or less change between the May 12 and May 19, 2026 crawls?", ["5.875", "6.25"], ["7.13"]),
        ("How did the 17-month certificate special APY change between June and August 2026?", ["3.85%", "3.95%"], ["4.10%"]),
        ("Did the 15-year fixed mortgage rate change between May 12 and May 19, 2026?", ["5.625", "6.000%"], ["6.75"]),
    ]
    for q, must, must_not in cases:
        assert _has(ks_full.answer(q).text, must, must_not), q

def test_change_endpoints_in_one_crawl_or_reversed(ks_full):
    one = ks_full.answer("How did the 30-year fixed mortgage rate for loans of $100,000 or less change between May 13 and May 18, 2026?")
    assert not one.confident and not one.sources and "unchanged" not in one.text
    fwd = ks_full.answer("How did the 17-month certificate special APY change between May and September 2026?").text
    rev = ks_full.answer("How did the 17-month certificate special APY change between September and May 2026?").text
    assert fwd == rev

def test_dev_change_items_still_score(ks_full):  # (pin)
    import json
    from scoring import score_item
    dev = {it["id"]: it for it in map(json.loads, open("eval/dev_extra.jsonl"))}
    for i in ("dev-007", "dev-008", "dev-009", "dev-010"):
        assert score_item(dev[i], ks_full.answer(dev[i]["question"], dev[i].get("as_of")))["score"] == 1.0, i
