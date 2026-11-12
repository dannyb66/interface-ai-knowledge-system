"""Reviewed v2 semantics survive ingestion, serialization and composition."""
from dataclasses import asdict, replace
import copy
import json

import pytest

from kb.claim_semantics import SourcePin, semantic_revision, semantics_survive
from kb.compose import render
from kb.prose_facts import ProseBook, parse_prose
from kb.registry import Registry
from kb.resolve import resolve
from kb.question import Query
from kb.source_pages import SourcePages, content_digest, source_page
from kb.store import FactStore
from kb.types import fact_from_dict, fact_to_dict

R = Registry.load()
SID = "05_2026-09-28_latest"
URL = "https://example.test/assistance"
FEE = "membership_reopening_within_six_months_of_closing_fee"
CONDITION = "Applicants must have income at or below 80% of the example published limit."


def entry(text=CONDITION, unit="percent", value=80, role="eligibility_condition", attribute="eligibility",
          product="mortgage_rate_relief", effective=None):
    pin = SourcePin(SID, URL, content_digest(text))
    semantic = {"version": 1, "claim_id": "example.threshold", "revision": semantic_revision(text, text, [pin], effective),
                "role": role, "comparator": "le" if role == "eligibility_condition" else "none",
                "basis": "example published limit" if role == "eligibility_condition" else "",
                "condition_group": "example.requirements" if role == "eligibility_condition" else "",
                "condition_logic": "single", "conditions": [text] if role == "eligibility_condition" else [],
                "numeric_unit": unit, "scale": ""}
    return {"canonical_urls": [URL], "crawls": [SID], "quote": text, "product_id": product, "attribute": attribute,
            "qualifiers": {}, "value": value, "value_text": text, "unit": unit, "claim_type": "assertion",
            "published_date": None, "event_date": None, "extractor": "curated", "effective_date": effective,
            "source_pins": [asdict(pin)], "semantics": semantic}


def parse_one(raw):
    return parse_prose({"_version": "test", "_schema_version": 2, "facts": [raw]}, R)


def fact_for(raw):
    pages = SourcePages([source_page(SID, URL, raw["quote"], fetched_at="2026-09-28")])
    facts = ProseBook(parse_one(raw)).facts(SID, pages)
    assert len(facts) == 1
    return facts[0]


def test_v2_threshold_survives_all_runtime_boundaries():
    fact = fact_for(entry())
    restored = fact_from_dict(json.loads(json.dumps(fact_to_dict(fact))))
    assert restored == fact
    assert restored.semantics.comparator == "le" and restored.semantics.basis == "example published limit"
    store = FactStore(); store.add(SID, "2026-09-28", [restored]); store.finalize()
    q = Query("value", "mortgage_rate_relief", "eligibility", (), None, False, "Eligibility requirements?", frozenset(), "test")
    plan = resolve(q, store, R)
    answer = render(plan)
    assert answer.confident and CONDITION in answer.text and plan.strict_numbers
    assert not semantics_survive("Applicants have income at 80%.", plan.facts)
    # A renderer/linter losing a clause must refuse, even when the number still grounds the answer.
    corrupted = replace(restored, value_text="80%")
    assert not semantics_survive("80%", [corrupted])
    with pytest.raises(ValueError, match="condition"):
        fact_from_dict(fact_to_dict(corrupted))


@pytest.mark.parametrize("change", [
    {"basis": "a different limit"}, {"role": "description"}, {"numeric_unit": "text"},
    {"comparator": "ge"}, {"comparator": "lt"}, {"conditions": ["Applicants also need a guarantor."]}, {"condition_group": ""},
])
def test_percentage_permission_is_not_blanket(change):
    raw = entry(); raw["semantics"].update(change)
    with pytest.raises(ValueError):
        parse_one(raw)


def test_v1_exact_schema_and_percentage_rejection_stay_intact():
    raw = entry()
    for field in ("effective_date", "semantics", "source_pins"):
        raw.pop(field)
    with pytest.raises(ValueError, match="contains a rate"):
        parse_prose({"_version": "test", "facts": [raw]}, R)
    with pytest.raises(ValueError, match="unknown fields"):
        parse_prose({"_version": "test", "facts": [entry()]}, R)


def test_spelled_out_percent_is_not_an_untyped_escape_hatch():
    text = "Applicants must have income at or below 80 percent of the example published limit."
    raw = entry(text, "text", None)
    raw["semantics"]["comparator"] = "none"
    with pytest.raises(ValueError, match="percentage eligibility"):
        parse_one(raw)
    fact = fact_for(entry())
    serialized = fact_to_dict(fact)
    serialized["source"]["quote"] = "An unrelated source statement."
    with pytest.raises(ValueError, match="source quote"):
        fact_from_dict(serialized)


def test_free_is_not_synthesized_money_and_fee_dates_are_preserved():
    free = fact_for(entry("The service is Free for members.", "free", None, "fee", "fee", FEE))
    assert free.value is None and free.unit == "free"
    raw = entry("The service is Free for members.", "free", 0, "fee", "fee", FEE)
    with pytest.raises(ValueError, match="invented"):
        parse_one(raw)
    dated = fact_for(entry("The reopening fee is $2.", "usd", 2, "fee", "fee", FEE, "2027-01-01"))
    store = FactStore(); store.add(SID, "2026-09-28", [dated]); store.finalize()
    assert not store.in_force(SID, FEE, "fee", "2026-09-28")
    assert store.in_force(SID, FEE, "fee", "2027-01-01") == [dated]
    q = Query("value", FEE, "fee", (), None, False, "What is the reopening fee?", frozenset(), "fee")
    assert not resolve(q, store, R).confident  # no as_of means current crawl, not a future effective price


def test_percentage_points_are_distinct_after_serialization():
    raw = entry("The program reduces the interest rate by 1.5 percentage points.", "percentage_points", 1.5,
                "benefit", "description", "mortgage_rate_relief")
    fact = fact_for(raw)
    assert fact_from_dict(json.loads(json.dumps(fact_to_dict(fact)))).unit == "percentage_points"
    wrong = copy.deepcopy(raw); wrong["unit"] = wrong["semantics"]["numeric_unit"] = "percent"
    with pytest.raises(ValueError):
        parse_one(wrong)
    assert not semantics_survive("The program reduces the interest rate by 1.5%.", [fact])
    from conftest import single_plan
    from kb.normalize import number_tokens
    plan = single_plan("yes_no", fact, frozenset(number_tokens(fact.value_text)),
                       question="Does the program reduce the interest rate by 1.5%?", strict_numbers=True)
    assert not render(plan).confident  # legacy number_tokens conflates 'percentage' with percent


def test_comparator_uses_primary_claim_not_another_condition():
    from kb.claim_semantics import primary_comparator
    assert primary_comparator("Income at or below 80% of the limit and a minimum of $10 saved.", 80, "percent") == "le"
    assert primary_comparator("Income at or above 80% of the limit.", 80, "percent") == "ge"
    assert primary_comparator("Income below 80% of the limit.", 80, "percent") == "lt"
    assert primary_comparator("Income above 80% of the limit.", 80, "percent") == "gt"
    assert primary_comparator("A minimum of $10 saved; the ratio is 80% of the limit.", 80, "percent") == "eq"
    with pytest.raises(ValueError, match="unambiguous"):
        primary_comparator("Income below 80% and expenses above 80%.", 80, "percent")


def test_stale_pin_or_revision_cannot_silently_accept_another_page():
    raw = entry(); raw["semantics"]["revision"] = "0" * 64
    with pytest.raises(ValueError, match="revision"):
        parse_one(raw)
    raw = entry()
    pages = SourcePages([source_page(SID, URL, raw["quote"] + " Extra text.")])
    assert ProseBook(parse_one(raw)).facts(SID, pages) == []


def test_legacy_fact_serialization_defaults_annotation_to_none():
    from conftest import make_fact
    fact = make_fact("share_savings", "apy", "1.00%", value=1)
    serialized = fact_to_dict(fact)
    assert "semantics" not in serialized and "page_id" not in serialized["source"]
    assert fact_from_dict(serialized) == fact


def test_typed_eligibility_verdict_preserves_all_conditions_and_is_not_personal():
    from conftest import single_plan
    text = "Applicants with membership and residency are eligible."
    raw = entry(text, "text", None)
    raw["semantics"].update(comparator="none", basis="", conditions=["membership", "residency"],
                            condition_logic="all")
    fact = fact_from_dict(fact_to_dict(fact_for(raw)))
    for question in ("Are applicants with membership or residency eligible?",
                     "Are applicants with membership eligible?", "Are we eligible?"):
        assert not render(single_plan("yes_no", fact, question=question, strict_numbers=True)).confident
    supported = render(single_plan("yes_no", fact,
        question="Are applicants with membership and residency eligible?", strict_numbers=True))
    assert supported.confident and not supported.text.startswith(("Yes.", "No.")) and text in supported.text
    ordinary = render(single_plan("value", fact, question="What are the requirements?", strict_numbers=True))
    assert ordinary.confident and text in ordinary.text


def test_free_fee_does_not_affirm_an_unsupported_numeric_price():
    from conftest import single_plan
    fact = fact_for(entry("The service is Free for members.", "free", None, "fee", "fee", FEE))
    answer = render(single_plan("yes_no", fact, question="Is the reopening fee $500?", strict_numbers=True))
    assert answer.confident and "Free for members" in answer.text
    assert not answer.text.startswith(("Yes.", "No.")) and "$500" not in answer.text
