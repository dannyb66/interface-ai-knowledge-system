"""Temporal typed prose retains every selected source date and distinct citation."""
from dataclasses import replace

import pytest

from conftest import make_fact
from kb.claim_semantics import ClaimSemantics
from kb.compose import render_with_dropped
from kb.normalize import number_tokens
from kb.question import Query
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_attribution import attribution
from kb.store import FactStore

OLD, NEW = "01_2026-05-12_baseline", "05_2026-09-28_latest"


def fixture(dated=True, same_text=False, same_publication=False):
    facts = []
    for sid, statement in ((OLD, "Example accepts paper applications."),
                           (NEW, "Example accepts paper applications." if same_text else "Example accepts online applications.")):
        published = (OLD if same_publication else sid)[3:13] if dated else None
        fact = make_fact("membership", "description", statement, snapshot_id=sid, unit="text",
                         extractor="curated", published=published)
        semantic = ClaimSemantics(1, "example.description", "0" * 64, "description", "none", "", "", "single",
                                  (statement,), "text", "")
        facts.append(replace(fact, source=replace(fact.source, quote=statement), semantics=semantic))
    store = FactStore()
    for fact in facts:
        store.add(fact.source.snapshot_id, fact.source.snapshot_id[3:13], [fact])
    store.finalize()
    return store, facts


@pytest.mark.parametrize("dated,same_text,same_publication", [
    (False, False, False), (True, False, False), (True, True, False), (True, True, True)])
@pytest.mark.parametrize("past", [False, True])
def test_temporal_prose_is_grounded_and_every_selected_crawl_is_cited(dated, same_text, same_publication, past):
    store, _ = fixture(dated, same_text, same_publication)
    query = Query("value" if past else "change", "membership", "description", (), None, False,
                  "What was the previous membership description?" if past else "How did the membership description change?",
                  frozenset(), "synthetic", past=past)
    plan = resolve(query, store, Registry.load())
    assert plan.confident and plan.facts
    answer, dropped = render_with_dropped(plan)
    assert answer.confident and not dropped
    assert number_tokens(answer.text) <= plan.permitted_values
    for fact in plan.facts:
        assert fact.value_text in answer.text and attribution(fact) in answer.text
    expected = {(s.citation_url or s.canonical_url, s.snapshot_id, s.quote) for s in plan.sources}
    assert {(s.url, s.snapshot_id, s.quote) for s in answer.sources} == expected
    if not past:
        assert {s.snapshot_id for s in answer.sources} == {OLD, NEW}
    if same_text:
        assert "unchanged" in answer.text


def test_equal_primary_number_cannot_hide_added_eligibility_condition():
    old = "Applicants need income at or below 80% of the limit."
    new = old + " Applicants must be residents."
    store = FactStore()
    for sid, statement in ((OLD, old), (NEW, new)):
        fact = make_fact("membership", "eligibility", statement, snapshot_id=sid, unit="percent",
                         value=80, extractor="curated")
        semantic = ClaimSemantics(1, "example.eligibility", "0" * 64, "eligibility_condition", "le", "the limit",
                                  "requirements", "all", tuple(statement.split(". ")), "percent", "")
        fact = replace(fact, source=replace(fact.source, quote=statement), semantics=semantic)
        store.add(sid, sid[3:13], [fact])
    store.finalize()
    for past in (False, True):
        query = Query("value" if past else "change", "membership", "eligibility", (), None, False,
                      "What were the previous membership requirements?" if past else "How did membership requirements change?",
                      frozenset(), "synthetic", past=past)
        plan = resolve(query, store, Registry.load())
        answer, dropped = render_with_dropped(plan)
        assert plan.confident and answer.confident and not dropped and "unchanged" not in answer.text
        assert old in answer.text
        assert ("must be residents" in answer.text) is not past


def test_missing_publication_date_permission_refuses_instead_of_dropping_attribution():
    store, _ = fixture()
    query = Query("change", "membership", "description", (), None, False, "How did the description change?",
                  frozenset(), "synthetic")
    plan = resolve(query, store, Registry.load())
    answer, _ = render_with_dropped(replace(plan, permitted_values=frozenset()))
    assert not answer.confident
