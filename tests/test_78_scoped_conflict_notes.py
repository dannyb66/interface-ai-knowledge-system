"""A history note belongs to its reviewed product scope and carries its evidence."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from contract import Answer, Source
from conftest import make_fact
from kb.conflicts import ConflictBook, answer_note, note_index, parse_curated, with_note
from kb.diagnostics import answer_dict
from kb.source_pages import SourcePages, source_page
from kb.types import AnswerPlan

OLD, NOW = "02_2026-05-19_recrawl", "05_2026-09-28_latest"
DAY = "2026-09-28"


def entry(**changes):
    return {"topic": "12-month regular certificate APY", "values": ["2.90%", "3.40%"],
            "resolution": "3.40%", "reason": "The reviewed rate changed after the older crawl.",
            "confidence": 1, "keys": [["cert_regular", "apy"]], "note_qualifiers": {"term_months": 12},
            "sources": [{"url": "https://example.test/rates?capture=old", "snapshot_id": OLD,
                         "value": "2.90%", "quote": "12 Month: 2.90% APY."},
                        {"url": "https://example.test/rates?capture=current", "snapshot_id": NOW,
                         "value": "3.40%", "quote": "12 Month: 3.40% APY."}], **changes}


def verified():
    book = ConflictBook(parse_curated({"conflicts": [entry()]}))
    for source in entry()["sources"]:
        book.observe(source["snapshot_id"], SourcePages([source_page(
            source["snapshot_id"], source["url"], source["quote"])]))
    return book.verified()


def fact(term=12, value=3.4):
    return make_fact("cert_regular", "apy", "{:.2f}%".format(value), value=value, term_months=term)


def plan(facts, **changes):
    return AnswerPlan("value", tuple(facts), frozenset(), (), True, None, NOW, crawl_date=DAY, **changes)


def test_scope_and_current_resolution_are_both_required():
    index = note_index(verified())
    assert answer_note(index, fact(12)) and "12-month" in answer_note(index, fact(12))
    for other in (fact(6), fact(24), fact(12, 2.9), replace(fact(), qualifiers=())):
        assert answer_note(index, other) is None


def test_all_selected_facts_are_checked_and_each_note_is_labeled_once():
    index = note_index(verified())
    answer = Answer("6 Month: 3.40%. 12 Month: 3.40%.", confident=True)
    result = with_note(answer, plan([fact(6), fact(12), fact(12)]), index)
    assert result.text == answer.text and result.conflict_note.count("12-month regular certificate APY") == 1
    assert "6-month" not in result.conflict_note
    assert with_note(answer, plan([fact(6)]), index) == answer


def test_supporting_citations_keep_raw_url_crawl_and_quote_identity():
    entries = verified(); current = entries[0].sources[-1]
    existing = Source(current.url, current.snapshot_id, current.quote)
    answer = Answer("3.40% APY.", sources=[existing], confident=True)
    result = with_note(answer, plan([fact()]), note_index(entries))
    triples = [(s.url, s.snapshot_id, s.quote) for s in result.sources]
    assert len(triples) == len(set(triples)) == 2
    assert set(triples) == {(s.url, s.snapshot_id, s.quote) for s in entries[0].sources}
    assert all("?capture=" in s.url for s in result.sources)
    assert answer.sources == [existing]  # the supplied answer is not mutated


def test_future_evidence_cannot_annotate_an_earlier_answer_with_the_same_number():
    index = note_index(verified()); answer = Answer("3.40% APY.", confident=True)
    old = replace(fact(), source=replace(fact().source, snapshot_id=OLD))
    assert answer_note(index, old) is None
    assert with_note(answer, plan([fact()], as_of="2026-08-27"), index) == answer
    assert with_note(answer, replace(plan([old]), snapshot_id=OLD, crawl_date="2026-05-19"), index) == answer


@pytest.mark.parametrize("scope", [[], {"unknown": 12}, {"term_months": "12"}, {"term_months": True},
                                    {"term_months": 0}, {"jumbo": "false"}, {"card": "visa"},
                                    {"balance_min": float("nan")}, {"balance_min": True}, {"term_months": [12]}])
def test_note_scope_rejects_non_scalar_or_invalid_qualifiers(scope):
    with pytest.raises(ValueError):
        parse_curated({"conflicts": [entry(note_qualifiers=scope)]})


def test_legacy_entries_remain_loadable_and_note_metadata_does_not_change_conflict_output():
    original = entry(); original.pop("note_qualifiers")
    legacy = parse_curated({"conflicts": [original]})[0]
    assert legacy.note_qualifiers == ()
    a, b = ConflictBook([legacy]), ConflictBook(parse_curated({"conflicts": [entry()]}))
    for source in entry()["sources"]:
        pages = SourcePages([source_page(source["snapshot_id"], source["url"], source["quote"])])
        a.observe(source["snapshot_id"], pages); b.observe(source["snapshot_id"], pages)
    assert a.emit() == b.emit()


def test_installed_certificate_note_scope_history_citations_and_cache_parity(ks_full):
    six = ks_full.answer("What is the APY on a 6-month regular certificate?")
    assert six.confident and "3.40%" in six.text and not six.conflict_note
    question = "What is the APY on a 12-month regular certificate?"
    current = ks_full.answer(question)
    assert current.confident and "12-month" in current.conflict_note and "2.90%" in current.conflict_note
    row = next(e for e in json.loads(Path("submission/data/conflicts_curated.json").read_text())["conflicts"]
               if e.get("note_qualifiers") == {"term_months": 12} and e["keys"] == [["cert_regular", "apy"]])
    assert {(s["url"], s["snapshot_id"], s["quote"]) for s in row["sources"]} <= {
        (s.url, s.snapshot_id, s.quote) for s in current.sources}
    for day in ("2026-05-19", "2026-06-09", "2026-08-27"):
        historical = ks_full.answer(question, day)
        assert historical.confident and not historical.conflict_note
        assert all(s.snapshot_id != NOW for s in historical.sources)
    before = dict(ks_full._answers)
    explanation = ks_full.explain(question)
    assert {"text": explanation["answer"], "sources": explanation["sources"],
            "confident": explanation["confident"], "conflict_note": explanation["conflict_note"]} == answer_dict(current)
    assert ks_full._answers == before
    current.sources.clear()
    assert ks_full.answer(question).sources
