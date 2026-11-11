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
# tests/test_11_prose.py (append)
def test_branch_phone_and_address_facts(store_full):
    phones = {dict(f.qualifiers)["branch_name"]: f.value_text for f in _facts(store_full, S05, "phone")}
    assert phones == {"cedar rapids": "(319) 366-8231", "platteville": "(608) 348-4499", "cedar falls": "(319) 277-3940",
                      "grimes": "(515) 320-7108", "east washington, madison": "(608) 282-6000", "mineral point road, madison": "(608) 282-6000"}
    assert [(dict(f.qualifiers)["branch_name"], f.value_text) for f in _facts(store_full, S05, "address") if f.extractor == "prose"] == [
        ("platteville", "1100 E. Business Highway 151")]

def test_branch_phone_answers(ks_full):
    assert "(608) 348-4499" in ks_full.answer("What is the phone number for the Platteville branch?").text
    for q in ("What is the phone number for the East Washington branch?", "What's the phone number of the Mineral Point Road branch in Madison?"):
        assert "(608) 282-6000" in ks_full.answer(q).text, q  # the two Madison branches share one number
    a = ks_full.answer("What is the phone number of the Mullan Avenue branch?")
    assert a.confident is False and not any(ch.isdigit() for ch in a.text)  # W5: an unlisted branch still refuses (pin)
