"""Typed percentage procedures retain all branches and dated event context."""
from dataclasses import asdict, replace
import copy
import json

import pytest

from kb.claim_semantics import SourcePin, semantic_revision, semantics_survive
from kb.compose import render
from kb.prose_facts import ProseBook, parse_prose
from kb.question import Query
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_pages import SourcePages, content_digest, source_page
from kb.store import FactStore
from kb.types import fact_from_dict, fact_to_dict

SID = "05_2026-09-28_latest"
URL = "https://example.test/guide"
R = Registry.load()


def entry(text, markdown, item, value, basis, comparator, role="procedure", published=None):
    pin = SourcePin(SID, URL, content_digest(markdown))
    unit = "percent" if "%" in text else "count"
    return {"canonical_urls": [URL], "crawls": [SID], "quote": text, "product_id": "mortgage_rate_relief",
            "attribute": "description", "qualifiers": {"item": item}, "value": value, "value_text": text,
            "unit": unit, "claim_type": "assertion", "published_date": published, "event_date": None,
            "extractor": "curated", "effective_date": None, "source_pins": [asdict(pin)],
            "semantics": {"version": 1, "claim_id": "example.claim." + str(item),
                "revision": semantic_revision(text, text, [pin], None), "role": role,
                "comparator": comparator, "basis": basis, "condition_group": "example.removal" if role == "procedure" else "",
                "condition_logic": "single", "conditions": [text], "numeric_unit": unit, "scale": ""}}


def facts(entries, markdown):
    book = ProseBook(parse_prose({"_version": "test", "_schema_version": 2, "facts": entries}, R))
    return book.facts(SID, SourcePages([source_page(SID, URL, markdown)]))


def answer(rows):
    store = FactStore(); store.add(SID, "2026-09-28", rows); store.finalize()
    query = Query("value", "mortgage_rate_relief", "description", (), None, False,
                  "What are the published steps?", frozenset(), "steps")
    return resolve(query, store, R)


def procedure():
    first = "At least 20% equity permits an appraisal request at the applicant's expense."
    second = "At 78% of the home value, an applicant may request removal without an appraisal."
    markdown = first + "\n" + second
    return [entry(first, markdown, 1, 20, "equity", "ge"),
            entry(second, markdown, 2, 78, "home value", "eq")], markdown


def test_two_reviewed_procedure_branches_survive_serde_and_render():
    entries, markdown = procedure()
    rows = [fact_from_dict(json.loads(json.dumps(fact_to_dict(f)))) for f in facts(entries, markdown)]
    plan = answer(rows)
    result = render(plan)
    assert result.confident
    assert all(raw["value_text"] in result.text for raw in entries)
    assert not semantics_survive(result.text.replace("at the applicant's expense", ""), rows)
    assert not answer(rows[:1]).confident


def test_missing_source_branch_does_not_yield_a_complete_procedure():
    entries, markdown = procedure()
    first = entries[0]
    entries[0] = entry(first["quote"], first["quote"], 1, 20, "equity", "ge")
    rows = facts(entries, first["quote"])
    assert len(rows) == 1 and not answer(rows).confident


@pytest.mark.parametrize("mutation", ["text_unit", "missing_basis", "missing_conditions", "mixed_values", "advertised_rate"])
def test_percentage_permission_is_bounded_to_reviewed_single_primary_claim(mutation):
    entries, markdown = procedure()
    raw = copy.deepcopy(entries[0])
    if mutation == "text_unit":
        raw.update(unit="text", value=None)
        raw["semantics"].update(numeric_unit="text", comparator="none")
    elif mutation == "missing_basis":
        raw["semantics"]["basis"] = ""
    elif mutation == "missing_conditions":
        raw["semantics"]["conditions"] = []
    else:
        text = raw["value_text"] + (" Another branch uses 78% of home value." if mutation == "mixed_values" else " The APR is advertised.")
        raw = entry(text, text, 1, 20, "equity", "ge")
    with pytest.raises(ValueError):
        parse_prose({"_version": "test", "_schema_version": 2, "facts": [raw]}, R)


@pytest.mark.parametrize("role", ["organization_fact", "description", "procedure"])
def test_dated_statement_keeps_source_attribution_and_strict_numbers(role):
    text = "The organization recognized 12 institutions."
    markdown = "June 2, 2021\n" + text
    raw = entry(text, markdown, 1, 12, "", "eq", role, "2021-06-02")
    rows = facts([raw], markdown)
    restored = fact_from_dict(json.loads(json.dumps(fact_to_dict(rows[0]))))
    plan = answer([restored]); result = render(plan)
    assert result.confident and "source published on June 2, 2021:" in result.text
    assert plan.strict_numbers and ("", 2021.0) in plan.permitted_values
    assert not semantics_survive(text, [restored])
    if role == "procedure":
        assert "source published on June 2, 2021:" in render(replace(plan, intent="how_to")).text
