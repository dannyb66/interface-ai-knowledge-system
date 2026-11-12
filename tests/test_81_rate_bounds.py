"""A loan-table lower bound is neither an exact rate nor a personal approval."""
from dataclasses import replace
import json

import pytest

from conftest import single_plan
from kb.blocks import split_blocks
from kb.compose import render, render_with_dropped
from kb.diagnostics import answer_dict
from kb.extract_rules import SourceContext, extract_block
from kb.normalize import number_tokens
from kb.registry import Registry, _rule
from kb.types import fact_from_dict, fact_to_dict


def extract(header="APR (As Low As)", rows="| Example | 4.75% |", trailer=""):
    markdown = "## Example\n| Product | " + header + " |\n| --- | --- |\n" + rows + "\n\n" + trailer
    product = {"product_id": "example", "family": "information", "segment": "personal",
               "names": ["Example"], "aliases": [], "attributes_published": ["apr", "apy", "rate"]}
    rule = _rule({"url_pattern": "", "section_pattern": "", "label_pattern": "^example$",
                  "product_id": "example", "qualifiers": {}}, 0, {"example": product})
    registry = Registry("synthetic", [product], [rule], [])
    context = SourceContext("https://example.test/rates", "https://example.test/rates", "rate_sheet", 3,
                            "05_2026-09-28_latest", "2026-09-28")
    table = next(b for b in split_blocks(markdown, frozenset()) if b.kind == "table")
    return extract_block(table, context, registry), markdown


def test_explicit_column_bound_keeps_numeric_cell_and_exact_header_context():
    facts, markdown = extract(rows="| Example | 4.75% |\n| Example | 5.25% |")
    for fact in facts:
        assert fact.rate_bound == "as_low_as" and fact.value_text in ("4.75%", "5.25%")
        assert fact.source.quote in markdown and "APR (As Low As)" in fact.source.quote
        assert fact_from_dict(json.loads(json.dumps(fact_to_dict(fact)))) == fact
        answer, dropped = render_with_dropped(single_plan("value", fact, number_tokens(fact.value_text)))
        assert answer.confident and "as low as " + fact.value_text + " APR" in answer.text and not dropped
        assert any("APR (As Low As)" in s.quote and fact.value_text in s.quote for s in answer.sources)


@pytest.mark.parametrize("header,trailer", [("APR", ""), ("APY", ""), ("Dividend Rate", ""),
    ("APR", "Rates may be as low as the quoted rate."), ("APY (As Low As)", "")])
def test_bounds_do_not_leak_from_other_attributes_or_unscoped_prose(header, trailer):
    (fact,), _ = extract(header, trailer=trailer)
    assert fact.rate_bound is None
    assert "rate_bound" not in fact_to_dict(fact)
    assert "as low as" not in render(single_plan("value", fact, number_tokens(fact.value_text))).text


@pytest.mark.parametrize("question", ["Is the Example APR exactly 4.75%?", "Will I get 4.75% APR on Example?",
    "Is my Example rate 7.00%?", "Is the Example APR below 7%?"])
def test_bound_never_produces_a_numeric_equality_or_personal_verdict(question):
    (fact,), _ = extract()
    answer = render(single_plan("yes_no", fact, number_tokens(fact.value_text) | number_tokens(question),
                                question=question))
    assert answer.confident and "as low as 4.75% APR" in answer.text
    assert not answer.text.startswith(("Yes.", "No.")) and "7.00%" not in answer.text


def test_bound_survives_rendering_or_the_entire_answer_refuses(monkeypatch):
    from kb import compose
    (fact,), _ = extract()
    monkeypatch.setitem(compose.RENDERERS, "value", lambda plan: "Example: 4.75% APR.")
    assert not render(single_plan("value", fact, number_tokens(fact.value_text))).confident


def test_serialization_rejects_unknown_bound_and_missing_source_context():
    (fact,), _ = extract()
    for changes in ({"rate_bound": "guaranteed"}, {"attribute": "apy"}, {"unit": "usd"},
                    {"value": None}, {"value": True}, {"source": replace(fact.source, quote="4.75% APR")}):
        with pytest.raises(ValueError):
            fact_from_dict(fact_to_dict(replace(fact, **changes)))
    wrong_column = "| Product | APR | Rate (As Low As) |\n| --- | --- | --- |\n| Example | 4.75% | 4.50% |"
    with pytest.raises(ValueError):
        fact_from_dict(fact_to_dict(replace(fact, source=replace(fact.source, quote=wrong_column))))


def test_each_selected_bounded_table_is_cited_even_at_the_same_url():
    (first,), _ = extract()
    (second,), _ = extract(rows="| Example | 5.25% |")
    plan = single_plan("list", first, number_tokens("4.75% 5.25%"))
    answer = render(replace(plan, facts=(first, second), sources=(first.source, second.source)))
    assert {s.quote for s in answer.sources} == {first.source.quote, second.source.quote}


@pytest.mark.parametrize("question,value", [
    ("What is the APR for a 60-month auto loan on a 2025 vehicle?", "5.39%"),
    ("What is the standard HELOC APR?", "6.25%"),
    ("What is the APR on a 60-month home equity loan?", "6.74%")])
def test_installed_loan_headers_reach_answers_sources_and_explain(ks_full, question, value):
    answer = ks_full.answer(question)
    assert answer.confident and "as low as " + value in answer.text
    assert any("As Low As" in s.quote and value in s.quote for s in answer.sources)
    explanation = ks_full.explain(question)
    assert answer_dict(answer) == {"text": explanation["answer"], "sources": explanation["sources"],
                                  "confident": explanation["confident"], "conflict_note": explanation["conflict_note"]}
    assert ks_full.answer(question) == answer


def test_installed_fixed_deposit_keeps_its_exact_value_and_verdict(ks_full):
    answer = ks_full.answer("Is the APY on a 6-month regular certificate 3.40%?")
    assert answer.confident and answer.text.startswith("Yes.") and "3.40%" in answer.text
    assert "as low as" not in answer.text


def test_all_ingested_bounds_roundtrip_with_their_own_header_and_cell(ks_full):
    facts = [f for snapshot in ks_full.store.by_product_attr.values() for values in snapshot.values()
             for f in values if f.rate_bound]
    assert facts
    for fact in facts:
        assert fact_from_dict(json.loads(json.dumps(fact_to_dict(fact)))) == fact
