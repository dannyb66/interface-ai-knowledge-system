"""A reviewed definition and its exclusions remain one complete description scope."""
from dataclasses import asdict, replace
import json

import pytest

from kb.claim_semantics import SourcePin, semantic_revision
from kb.compose import render
from kb.prose_facts import ProseBook, parse_prose
from kb.question import Query
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_pages import SourcePages, content_digest, source_page
from kb.store import FactStore
from kb.types import fact_from_dict, fact_to_dict

SID, DAY, GROUP = "05_2026-09-28_latest", "2026-09-28", "example.complete_description"
R = Registry.load()


def catalog(required=("example.definition", "example.exclusion"), snapshot_id=SID):
    entries, pages = [], []
    for item, (identity, text) in enumerate((
            ("example.definition", "This service provides account protection."),
            ("example.exclusion", "Coverage excludes pre-existing conditions.")), 1):
        url = "https://example.test/description-" + str(item)
        pin = SourcePin(snapshot_id, url, content_digest(text))
        entries.append({"canonical_urls": [url], "crawls": [snapshot_id], "quote": text, "product_id": "membership",
            "attribute": "description", "qualifiers": {"item": item}, "value": None, "value_text": text,
            "unit": "text", "claim_type": "assertion", "published_date": None, "event_date": None,
            "effective_date": None, "extractor": "curated", "source_pins": [asdict(pin)],
            "semantics": {"version": 1, "claim_id": identity,
                "revision": semantic_revision(text, text, [pin], None), "role": "description",
                "comparator": "none", "basis": "", "condition_group": GROUP, "condition_logic": "single",
                "conditions": [text], "numeric_unit": "text", "scale": ""}})
        pages.append(source_page(snapshot_id, url, text))
    return {"_version": "test", "_schema_version": 2, "facts": entries, "claim_groups": [
        {"entity": "membership", "attribute": "description", "claim_set": GROUP,
         "crawls": [snapshot_id], "required_claim_ids": list(required)}]}, pages


def answer(facts):
    store = FactStore(); store.add(SID, DAY, facts); store.finalize()
    query = Query("value", "membership", "description", (), None, False, "Describe membership", frozenset(), "q")
    return render(resolve(query, store, R))


def test_explicit_description_bundle_survives_serde_and_preserves_exclusion():
    data, pages = catalog()
    facts = ProseBook(parse_prose(data, R)).facts(SID, SourcePages(pages))
    restored = [fact_from_dict(json.loads(json.dumps(fact_to_dict(f)))) for f in facts]
    result = answer(restored)
    assert restored == facts and result.confident
    assert all(f.value_text in result.text for f in facts)


@pytest.mark.parametrize("loss", ["source", "selection", "authority"])
def test_missing_exclusion_refuses_the_whole_description(loss):
    data, pages = catalog(); book = ProseBook(parse_prose(data, R))
    facts = book.facts(SID, SourcePages(pages[:1] if loss == "source" else pages))
    if loss == "selection":
        facts = facts[:1]
    elif loss == "authority":
        facts[1] = replace(facts[1], source=replace(facts[1].source, authority=-1))
    assert not answer(facts).confident


def test_declaration_cannot_remove_a_known_caveat_in_the_same_bundle():
    data, pages = catalog(required=("example.definition",))
    facts = ProseBook(parse_prose(data, R)).facts(SID, SourcePages(pages))
    assert {c for g in facts[0].claim_groups for c in g.required_claim_ids} == {
        "example.definition", "example.exclusion"}
    assert not answer(facts[:1]).confident


def test_missing_declared_claim_and_unannotated_alternative_cannot_bypass_completeness():
    data, pages = catalog(required=("example.definition", "example.exclusion", "example.unavailable_caveat"))
    book = ProseBook(parse_prose(data, R)); facts = book.facts(SID, SourcePages(pages))
    assert not answer(facts).confident
    alternative = replace(facts[0], semantics=None, claim_groups=(), extractor="rules",
                          source=replace(facts[0].source, authority=10))
    assert not answer(book.bind_groups(SID, facts + [alternative])).confident


def test_description_group_requires_explicit_declaration_and_matching_reviewed_annotations():
    data, pages = catalog(); data.pop("claim_groups")
    assert all(not e.claim_groups for e in parse_prose(data, R))
    for role, group in (("description", ""), ("description", "another.group"), ("benefit", GROUP)):
        data, _ = catalog()
        data["facts"][1]["semantics"].update(role=role, condition_group=group)
        with pytest.raises(ValueError, match="matching condition_group"):
            parse_prose(data, R)


def test_unresolved_earlier_requirement_cannot_borrow_a_complete_later_bundle():
    earlier = "01_2026-05-12_baseline"
    old_data, old_pages = catalog(required=("example.unresolved_earlier_source",), snapshot_id=earlier)
    new_data, new_pages = catalog()
    store = FactStore()
    for sid, day, data, pages in ((earlier, "2026-05-12", old_data, old_pages), (SID, DAY, new_data, new_pages)):
        store.add(sid, day, ProseBook(parse_prose(data, R)).facts(sid, SourcePages(pages)))
    store.finalize()
    query = Query("value", "membership", "description", (), "2026-05-12", False,
                  "Describe membership", frozenset(), "earlier")
    old = resolve(query, store, R)
    assert not old.confident and not old.facts and not render(old).sources
    assert render(resolve(replace(query, as_of=DAY), store, R)).confident
