"""Narrow display cleanup cannot erase substantive conditions or comparisons."""
from dataclasses import replace
import re

import pytest

from conftest import make_fact
from kb.claim_semantics import ClaimSemantics, semantics_survive
from kb.compose import render
from kb.normalize import number_tokens
from kb.prose_presentation import prose_statement
from kb.types import AnswerPlan


def fact(text):
    result = make_fact("membership", "description", text, unit="text", extractor="curated")
    semantics = ClaimSemantics(1, "example.prose", "0" * 64, "procedure", "none", "", "example.bundle",
                               "single", (text,), "text", "")
    return replace(result, semantics=semantics)


@pytest.mark.parametrize("source,expected", [
    ('The source explains. > "Coverage applies only after deposit."',
     'The source explains. "Coverage applies only after deposit."'),
    ('> "Coverage applies only after deposit."', '"Coverage applies only after deposit."'),
    (r'Choose an appointment location. (Required)\* Branch, phone or online.',
     'Choose an appointment location. (Required) Branch, phone or online.'),
    (r'#### \|2\| Verify identity only after deposit.',
     '#### |2| Verify identity only after deposit.'),
    (r'Check the listing. #### \|3\| Proceed only after deposit.',
     'Check the listing. #### |3| Proceed only after deposit.'),
])
def test_known_markers_can_render_but_every_condition_remains_required(source, expected):
    row = fact(source)
    plan = AnswerPlan("value", (row,), frozenset(number_tokens(source)), (row.source,), True, None,
                      row.source.snapshot_id, strict_numbers=True)
    answer = render(plan)
    assert answer.confident and expected in answer.text and prose_statement(source) == expected
    required = "only after deposit" if "deposit" in source else "(Required)"
    assert not semantics_survive(answer.text.replace(required, ""), [row])


def test_heading_cleanup_preserves_ordinal_and_every_word():
    source = r'#### \|2\| Verify identity before proceeding.'
    row = fact(source)
    text = prose_statement(source)
    assert number_tokens(text) == number_tokens(source)
    assert not semantics_survive(text.replace('|2|', '|3|'), [row])
    assert not semantics_survive(text.replace('before proceeding', ''), [row])
    assert prose_statement(r'Use \|2\| as the account code.') == r'Use \|2\| as the account code.'


def test_installed_numbered_procedure_keeps_all_claims_and_sources(ks_full):
    text = 'Explain curbstoning and the steps for checking a used car seller.'
    answer = ks_full.answer(text)
    assert answer.confident
    headings = {n for source in answer.sources for n in re.findall(r'\\\|(\d+)\\\|', source.quote)}
    assert headings and all('|{}|'.format(n) in answer.text for n in headings)
    assert len(answer.sources) == 6
    assert ks_full.explain(text)['answer'] == answer.text


@pytest.mark.parametrize("statement", ["Balance > $100.", "Amount < $100.", "Coverage* is conditional.",
                                        "Select an option*.", "> Coverage requires approval."])
def test_other_asterisks_and_comparators_are_not_approved_residue(statement):
    assert prose_statement(statement) == statement
    assert not semantics_survive(statement.replace(">", "").replace("<", "").replace("*", ""), [fact(statement)])
