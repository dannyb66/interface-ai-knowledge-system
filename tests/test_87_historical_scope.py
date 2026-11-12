"""Synthetic controls for publication scope, incomplete notices and named sites."""
from dataclasses import replace

import pytest

from conftest import make_fact
from kb.compose import render
from kb.conflicts import ConflictBook, note_index, parse_curated, with_note
from kb.historical_scope import historical_scope_supported, serving_date_text, source_reference
from kb.normalize import number_tokens
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_pages import SourcePages, source_page
from kb.store import FactStore
from kb.types import AnswerPlan, ClaimType
from contract import Answer

R = Registry.load()
SID = "05_2026-09-28_latest"
DAY = "2026-09-28"


def fact(attribute, value, published="2022-04-07", branch="maple", quote=None, **kwargs):
    item = make_fact("branch", attribute, value, published=published, branch_name=branch,
                     unit="text", extractor="prose", claim=ClaimType.ASSERTION,
                     url="https://example.test/newsroom/maple-notice", page_type="newsroom", **kwargs)
    return replace(item, source=replace(item.source, quote=quote or value))


def store(*facts):
    result = FactStore()
    result.add(SID, DAY, facts)
    result.finalize()
    return result


def answer(question, facts, as_of=DAY):
    query = parse(question, as_of, R)
    plan = resolve(query, store(*facts), R)
    return query, plan, render(plan)


@pytest.mark.parametrize("question, expected", [
    ("In the April 7, 2022 Maple Learning Lab notice, what phone was listed?", ("2022-04-07",)),
    ("What address was in the 2022 Maple expansion notice?", ("2022",)),
    ("What honor did the organization announce in April 2022?", ("2022-04",)),
    ("According to the April 2022 notice, when would it close in July 2023?", ("2022-04",)),
    ("In the April 2022 story captured in September 2026, what happened?", ("2022-04",)),
    ("What phone number is listed for the Maple branch?", None),
    ("According to the branch notice, when would it close?", ()),
    ("According to the notice, would the branch close in July 2023?", ()),
    ("What happened in the February 30, 2022 announcement?", ("invalid",)),
])
def test_source_date_is_separate_from_serving_or_event_date(question, expected):
    assert source_reference(question) == expected


@pytest.mark.parametrize("noun", ["notices", "announcements", "articles", "reports", "stories", "posts", "releases"])
def test_plural_source_nouns_preserve_their_publication_scope(noun):
    question = "What phone was listed in the April 2023 {} for the Maple branch?".format(noun)
    assert source_reference(question) == ("2023-04",)
    assert not historical_scope_supported(parse(question, DAY, R), [fact("phone", "555-010-0123")])


def test_matching_plural_announcement_reference_keeps_historical_attribution():
    _, _, result = answer("What phone was listed in the April 2022 announcements for the Maple branch?",
                           [fact("phone", "555-010-0123")])
    assert result.confident and "source published on April 7, 2022" in result.text
    assert "As of September" not in result.text


def test_publication_mask_preserves_same_year_serving_date_and_capture_date():
    question = "As of July 2022, what did the April 2022 branch notice say?"
    masked = serving_date_text(question)
    assert len(masked) == len(question) and "July 2022" in masked and "April 2022" not in masked
    captured = "In the April 2022 story captured in September 2026, what happened?"
    assert "September 2026" in serving_date_text(captured)


@pytest.mark.parametrize("question", [
    "How did the report change between May 2026 and September 2026?",
    "Compare the annual report from May 2026 to September 2026.",
    "What changed since May 2026 in the annual report?",
    "What was reported until May 2026 in the branch notice?",
])
def test_comparison_windows_and_cutoffs_are_not_publication_dates(question):
    assert source_reference(question) in (None, ())
    assert serving_date_text(question) == question


def test_historical_phone_uses_actual_publication_and_keeps_serving_date():
    question = "What phone number did the April 2022 notice list for the Maple branch?"
    query, plan, result = answer(question, [fact("phone", "555-010-0123")])
    assert query.as_of == DAY and plan.as_of == DAY and plan.snapshot_id == SID
    assert result.confident and "In the source published on April 7, 2022:" in result.text
    assert "phone number was listed as 555-010-0123" in result.text
    assert "As of September" not in result.text
    assert ("", 7.0) in plan.permitted_values  # the day came from metadata, not the question


def test_omitted_serving_date_does_not_turn_publication_into_as_of():
    query, plan, result = answer("What phone did the April 7, 2022 notice list for the Maple branch?",
                                 [fact("phone", "555-010-0123")], as_of=None)
    assert query.as_of is None and plan.as_of is None
    assert result.confident and "April 7, 2022" in result.text


def test_current_phone_lookup_preserves_existing_scalar_behavior():
    query, _, result = answer("What is the phone number for the Maple branch?", [fact("phone", "555-010-0123")])
    assert query.as_of == DAY and result.confident
    assert result.text == "As of September 2026, Call the Maple branch at 555-010-0123."


@pytest.mark.parametrize("question, row, wording", [
    ("What address did the April 2022 notice list for the Maple branch?",
     fact("address", "12 Example Road"), "address was listed as 12 Example Road"),
    ("What were the Maple branch Saturday lobby hours in the April 2022 notice?",
     fact("lobby_hours", "9 a.m.-noon", day="saturday"), "Saturday 9 a.m.-noon"),
])
def test_single_historical_contact_attribute_stays_answerable(question, row, wording):
    _, _, result = answer(question, [row])
    assert result.confident and wording in result.text
    assert "source published on April 7, 2022" in result.text and "As of September" not in result.text


@pytest.mark.parametrize("published", [None, "2021-04-07", "2022-05-07", "2023-04-07"])
def test_source_month_mismatch_or_missing_date_refuses(published):
    _, _, result = answer("What phone did the April 2022 notice list for the Maple branch?",
                           [fact("phone", "555-010-0123", published=published)])
    assert not result.confident and "I can't confirm" in result.text
    assert "555" not in result.text and not result.sources


@pytest.mark.parametrize("question", [
    "In April 2023, what phone did the Maple branch notice list?",
    "In April 2023 what phone did the Maple branch notice list?",
    "During 2023 what phone did the Maple branch notice list?",
])
def test_leading_ambiguous_source_date_cannot_silently_drop_its_year(question):
    _, _, result = answer(question, [fact("phone", "555-010-0123")])
    assert not result.confident and "555" not in result.text
    assert serving_date_text(question) == question  # ambiguous binding never becomes source metadata


def test_true_serving_date_does_not_require_same_publication_month():
    question = "As of September 2026, what phone did the Maple branch notice list?"
    _, _, result = answer(question, [fact("phone", "555-010-0123")])
    assert result.confident and "source published on April 7, 2022" in result.text


@pytest.mark.parametrize("question", [
    "What address and phone number did the 2022 Maple branch notice list?",
    "According to the 2022 notice, where could I find or call the Maple branch?",
    "What phone number and Saturday hours did the 2022 Maple branch notice list?",
    "In the 2022 notice, when were the Maple branch lobby and drive-up open Saturday, and how could I call it?",
    "According to the 2022 notice, when would the Maple branch close, and where could members get the same services?",
])
def test_incomplete_historical_multiattribute_request_never_returns_one_scalar(question):
    rows = [fact("phone", "555-010-0123"), fact("address", "12 Example Road"),
            fact("lobby_hours", "9 a.m.-noon", day="saturday"),
            fact("driveup_hours", "8 a.m.-noon", day="saturday"),
            fact("closure_date", "July 1, 2023", event="2023-07-01",
                 quote="This location will close July 1, 2023.")]
    _, _, result = answer(question, rows)
    assert not result.confident and "I can't confirm" in result.text
    assert number_tokens(result.text) <= number_tokens(question)


def test_notice_closure_remains_planned_after_event_date():
    rows = [fact("closure_date", "July 1, 2023", event="2023-07-01",
                 quote="This location will close July 1, 2023.")]
    _, _, result = answer("According to the April 2022 notice, when would the Maple branch close?", rows)
    assert result.confident and "source published on April 7, 2022" in result.text
    assert "was scheduled to close on July 1, 2023" in result.text
    assert "branch closed on" not in result.text
    # The existing current status contract remains in force outside source questions.
    _, _, current = answer("When did the Maple branch close?", rows)
    assert current.confident and "closed on July 1, 2023" in current.text


def test_prior_source_can_announce_an_event_after_the_serving_cutoff():
    rows = [fact("closure_date", "July 1, 2027", published="2026-04-07", event="2027-07-01",
                 quote="This location will close July 1, 2027.")]
    query, _, result = answer("According to the April 2026 notice, when would the Maple branch close?", rows)
    assert query.as_of == DAY and result.confident
    assert "was scheduled to close on July 1, 2027" in result.text
    assert "branch closed on" not in result.text


def test_unknown_named_lab_cannot_fall_back_to_generic_branch_list():
    rows = [fact("address", "12 Example Road", branch="maple", published=None),
            fact("address", "34 Sample Lane", branch="birch", published=None)]
    _, _, generic = answer("Where are Dupaco branches?", rows)
    assert generic.confident and "12 Example Road" in generic.text and "34 Sample Lane" in generic.text
    for question in ("Where is the Willow Innovation Lab?",
                     "Where is the willow innovation lab, and is it a full-service branch?"):
        _, _, result = answer(question, rows)
        assert not result.confident and not result.sources
        assert "Example Road" not in result.text and "Sample Lane" not in result.text


def test_recognized_learning_lab_scope_does_not_borrow_other_branch_facts():
    question = "What phone was in the 2022 Maple Learning Lab notice?"
    query = parse(question, DAY, R)
    own = fact("phone", "555-010-0123")
    other = fact("phone", "555-010-0456", branch="birch")
    assert historical_scope_supported(query, [own])
    assert not historical_scope_supported(query, [other])
    assert not historical_scope_supported(query, [own, other])


def test_one_source_cannot_satisfy_two_different_requested_publications():
    question = "What phone did the 2021 notice and the 2022 notice list for the Maple branch?"
    assert source_reference(question) == ("2021", "2022")
    assert not historical_scope_supported(parse(question, DAY, R), [fact("phone", "555-010-0123")])


def test_article_scalar_cannot_acquire_current_conflict_note_or_its_citations():
    raw = {"topic": "employee count", "values": ["14 employees", "20 employees"],
           "resolution": "20 employees", "reason": "The newer report states the latter count.",
           "confidence": 1, "keys": [["employee_count", "count"]],
           "sources": [{"url": "https://example.test/old-report", "snapshot_id": "01_2026-05-12_baseline",
                        "value": "14 employees", "quote": "There were 14 employees."},
                       {"url": "https://example.test/new-report", "snapshot_id": SID,
                        "value": "20 employees", "quote": "There were 20 employees."}]}
    book = ConflictBook(parse_curated({"conflicts": [raw]}))
    for source in raw["sources"]:
        book.observe(source["snapshot_id"], SourcePages([source_page(source["snapshot_id"], source["url"], source["quote"])]))
    index = note_index(book.verified())
    row = make_fact("employee_count", "count", "20 employees", value=20, unit="count", published="2022-04-07")
    plan = AnswerPlan("count", (row,), frozenset(), (), True, None, SID, as_of=DAY, crawl_date=DAY,
                      question="How many employees did the April 2022 report list?")
    original = Answer("The source published on April 7, 2022 listed 20 employees.", confident=True)
    conflicts = book.emit()
    assert len(conflicts) == 1 and with_note(original, plan, index) == original
    current = with_note(original, replace(plan, question="How many employees does Dupaco have?"), index)
    assert "20 employees is current" in current.conflict_note and len(current.sources) == 2
    assert book.emit() == conflicts  # answer-note scope does not change the official conflict API
