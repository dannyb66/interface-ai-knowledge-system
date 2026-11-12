"""Instrumentation observes actual decisions without changing their result."""
from dataclasses import replace
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

from kb.diagnostics import ResolutionTrace, answer_dict
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.store import FactStore
from conftest import make_fact

R = Registry.load()
SID = "05_2026-09-28_latest"


def test_parser_evidence_does_not_change_query_or_defaults():
    trace = ResolutionTrace()
    question = "What is the APY on Share Savings?"
    q = parse(question, None, R, trace=trace)
    assert q == parse(question, None, R)
    assert trace.parser["entity"]["origin"] == "explicit"
    assert trace.parser["attribute"]["origin"] == "explicit"
    assert trace.parser["intent"]["origin"] == "default"
    assert trace.parser["qualifiers"]["segment"]["origin"] == "default"
    assert trace.parser["as_of"]["evidence"] == "latest crawl"
    trace = ResolutionTrace()
    parse(question, "garbage", R, trace=trace)
    assert trace.parser["as_of"]["origin"] == "explicit"


@pytest.mark.parametrize("question,as_of,reason", [
    ("What is the APY on Share Savings?", "invalid", "malformed_date"),
    ("What is the APY on Unknown Zorb Savings?", None, "unknown_entity"),
    ("What is the APR on Share Savings?", None, "unpublished_attribute"),
    ("What is the business HELOC APR?", None, "unavailable_segment"),
    ("What is the APY on Share Savings?", None, "no_eligible_crawl"),
])
def test_guard_refusal_causes_are_distinct(question, as_of, reason):
    trace = ResolutionTrace()
    q = parse(question, as_of, R, trace=trace)
    store = FactStore()
    traced = resolve(q, store, R, trace)
    assert traced == resolve(q, store, R) and not traced.confident
    assert trace.refusals[-1]["reason"] == reason


def test_candidate_trace_records_actual_date_authority_and_tier_cuts():
    high = make_fact("auto_loan", "apr", "3.00%", value=3, term_months=60)
    low = replace(high, value=9, value_text="9.00%", source=replace(high.source, authority=0))
    future = replace(high, value=8, value_text="8.00%", effective_date="2027-01-01")
    wrong_term = replace(high, key=("auto_loan", "apr", (("term_months", 36),)), qualifiers=(("term_months", 36),))
    store = FactStore()
    store.add(SID, "2026-09-28", [future, low, high, wrong_term]); store.finalize()
    q = parse("What is the APR for a 60-month auto loan?", "2026-09-28", R)
    trace = ResolutionTrace()
    traced = resolve(q, store, R, trace)
    assert traced == resolve(q, store, R)
    steps = trace.steps
    assert next(s for s in steps if s["stage"] == "effective_date")["rejected_ids"]
    assert next(s for s in steps if s["stage"] == "authority")["rejected_ids"]
    assert next(s for s in steps if s["stage"] == "exact_or_tiers")["rejected_ids"]
    assert len(trace.candidates) == 4


def test_unavailable_program_has_its_own_refusal_reason():
    fact = make_fact("mortgage_purchase", "apr", "5.00%", value=5, program="fixed")
    store = FactStore(); store.add(SID, "2026-09-28", [fact]); store.finalize()
    q = parse("What is the ARM mortgage APR?", None, R)
    trace = ResolutionTrace()
    assert not resolve(q, store, R, trace).confident
    assert trace.refusals[-1]["reason"] == "unavailable_program"


def test_explain_matches_facade_and_does_not_touch_answer_cache(ks_full, public_items):
    for item in public_items:
        answer = ks_full.answer(item["question"], item.get("as_of"))
        before = dict(ks_full._answers)
        info = ks_full.explain(item["question"], item.get("as_of"))
        assert {"text": info["answer"], "sources": info["sources"], "confident": info["confident"],
                "conflict_note": info["conflict_note"]} == answer_dict(answer)
        assert ks_full._answers == before
        assert set(info["timings_ms"]) == {"parse", "resolve", "render"}
        json.dumps(info)


def test_diagnostic_tool_refuses_sealed_paths_before_reading(tmp_path):
    spec = importlib.util.spec_from_file_location("diagnose", Path("scripts/diagnose_generalization.py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="sealed"):
        module.checked_input(tmp_path / "blind" / "nonexistent.jsonl", {"partition": "development"}, "questions_sha256")
    with pytest.raises(ValueError, match="partition"):
        module.checked_input(tmp_path / "nonexistent.jsonl", {"partition": "blind"}, "questions_sha256")
    data = b'{"id":"example","question":"A synthetic question?"}\n'
    path = tmp_path / "dev.questions.jsonl"; path.write_bytes(data)
    manifest = {"schema_version": "phase4-dev-source-gold-v1", "artifact_sha256": {
        "dev.questions.jsonl": hashlib.sha256(data).hexdigest()}}
    assert module.checked_input(path, manifest, "questions_sha256") == data
    path.write_bytes(data + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        module.checked_input(path, manifest, "questions_sha256")
