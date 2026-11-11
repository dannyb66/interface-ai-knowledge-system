# tests/test_96_eval_sets.py
import json
import re
from pathlib import Path
from scoring import score_item
from contract import Answer

PUBLIC_KEYS = {"id","question","as_of","expected_answer","must_include","must_not_include","category","difficulty","weight","expected_sources","group"}

def _rows(p): return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]

def test_locked_set_schema():
    rows = _rows("eval/locked/locked_set.jsonl")
    assert 25 <= len(rows) <= 40 and len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert set(r) == PUBLIC_KEYS and (r["must_include"] or r["category"] == "should_refuse")
        assert isinstance(score_item(r, Answer(text="", confident=False))["score"], float)

def test_dev_set_schema():
    rows = _rows("eval/dev_extra.jsonl")
    assert len(rows) == 20 and all(r["id"].startswith("dev-") for r in rows)

UNIT = re.compile(r"[%$]|\b(?:\d[\d,.]*|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+[A-Za-z]")

def test_conflicts_gold_dev_format():
    gold = json.load(open("eval/conflicts_gold_dev.json")); ev = json.load(open("eval/conflicts_gold_dev_evidence.json"))
    assert 12 <= len(gold) <= 25 and len({g["id"] for g in gold}) == len(gold)
    for g in gold:
        assert set(g) == {"id", "topic_keywords", "values", "correct_value"}, g["id"]
        assert 2 <= len(g["values"]) <= 4 and all(UNIT.search(v) for v in g["values"]), g["id"]
        assert g["topic_keywords"] and all(k == k.lower() for k in g["topic_keywords"]), g["id"]
        assert g["correct_value"] is None or g["correct_value"] in g["values"], g["id"]
        assert sorted(r["value"] for r in ev[g["id"]]) == sorted(g["values"]), g["id"]
