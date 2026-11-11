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
from kb.temporal import select_dated

def _winner(store, sid, pid):
    fs = select_dated(store.by_product_attr[sid].get((pid, "count"), []), None)
    return [(dict(f.qualifiers).get("year"), f.value_text, f.published_date) for f in fs]

def test_count_facts(store_full):
    assert _winner(store_full, S05, "branch_count") == [(None, "22 branch office locations", "2026-05-05")]
    assert _winner(store_full, S05, "employee_count") == [(None, "over 600 employees", "2026-05-05")]
    assert _winner(store_full, S05, "county_count") == [(None, "118 counties throughout Iowa, northwest Illinois and southwest Wisconsin", "2026-05-05")]
    assert not {pid for pid, _ in store_full.by_product_attr[S05]} & {"member_count", "total_assets"}  # boilerplate member and asset counts stay out (pin)
    assert sorted(_winner(store_full, S05, "vto_users")) == [(2023, "294 Dupaco employees", "2024-04-19"), (2024, "256 Dupaco employees", "2025-04-21")]
    assert sorted(_winner(store_full, S05, "volunteer_hours")) == [(2023, "7,260 hours", "2024-04-19"), (2024, "6,187 hours", "2025-04-21")]

# tests/test_45_prose_answers.py (append)
import json

def test_branch_count_series_by_publication_date(ks_full):
    want = {None: "22", "2026-03-31": "23", "2025-12-31": "23", "2024-08-31": "24", "2022-12-31": "22", "2022-05-31": "20", "2022-01-31": "19"}
    for as_of, n in want.items():
        t = ks_full.answer("How many branches does Dupaco have?", as_of).text
        assert "Branch Count: {} branch office locations.".format(n) in t and t.count("branch office locations") == 1, as_of

def test_branch_count_items(ks_full, public_items):
    dev = {it["id"]: it for it in map(json.loads, open("eval/dev_extra.jsonl"))}
    for it in (_item(public_items, "dup-073"), dev["dev-015"]):
        assert _score(ks_full, it) == 1.0 and "24 branch" not in ks_full.answer(it["question"]).text

def test_vto_by_year(ks_full, public_items):
    dev = {it["id"]: it for it in map(json.loads, open("eval/dev_extra.jsonl"))}
    assert _score(ks_full, dev["dev-020"]) == 1.0 and "294" not in ks_full.answer(dev["dev-020"]["question"]).text
    assert ks_full.answer("How many Dupaco employees used Volunteer Time Off last year?").text.splitlines() == [
        "Volunteer Time Off, 2024: 256 Dupaco employees.", "Volunteer Time Off, 2023: 294 Dupaco employees."]
    assert _score(ks_full, _item(public_items, "dup-088")) == 1.0

def test_count_year_without_fact_refuses(ks_full):  # (pin)
    a = ks_full.answer("How many Dupaco employees used Volunteer Time Off in 2025?")
    assert a.confident is False and "256" not in a.text and "294" not in a.text

def test_other_counts(ks_full):
    for q, token in (("How many hours did Dupaco employees volunteer in 2024?", "6,187"), ("How many hours did Dupaco employees volunteer in 2023?", "7,260"),
                     ("How many employees does Dupaco have?", "600"), ("How many counties does Dupaco serve?", "118"),
                     ("How many branches did Dupaco have in 2022?", "22 branch office locations")):
        assert token in ks_full.answer(q).text, q
    assert ks_full.answer("How many members does Dupaco have?").confident is False  # member counts stay out, gap research #10 (pin)

# tests/test_26_question_gate.py (append)
def test_count_routes():
    cases = {"How many Dupaco employees used Volunteer Time Off in 2024?": ("vto_users", 2024),
             "How many Dupaco employees used Volunteer Time Off last year?": ("vto_users", None),
             "How many hours did Dupaco employees volunteer in 2024?": ("volunteer_hours", 2024),
             "How many employees does Dupaco have?": ("employee_count", None),
             "How many branches did Dupaco have in 2022?": ("branch_count", 2022),
             "What's the APR for a 60-month auto loan on a 2026 car?": ("auto_loan", None)}  # a model year is no year slot
    for q, (pid, year) in cases.items():
        p = parse(q, None, R)
        assert (p.product_id, dict(p.slots).get("year")) == (pid, year), q
