"""Losing one independently sourced eligibility requirement must not yield a partial answer."""
from dataclasses import asdict, replace
import json
import pytest

from kb.claim_groups import claim_identity, complete_groups
from kb.claim_semantics import SourcePin, semantic_revision
from kb.prose_facts import ProseBook, parse_prose
from kb.question import Query
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_pages import SourcePages, content_digest, source_page
from kb.store import FactStore
from kb.types import fact_from_dict, fact_to_dict

SID = "05_2026-09-28_latest"
URL = "https://example.test/requirements"
R = Registry.load()


def raw(text, identity, item, markdown):
    pin = SourcePin(SID, URL, content_digest(markdown))
    return {"canonical_urls": [URL], "crawls": [SID], "quote": text, "product_id": "membership",
            "attribute": "eligibility", "qualifiers": {"item": item}, "value": None, "value_text": text,
            "unit": "text", "claim_type": "assertion", "published_date": None, "event_date": None,
            "extractor": "curated", "effective_date": None, "source_pins": [asdict(pin)],
            "semantics": {"version": 1, "claim_id": identity,
                "revision": semantic_revision(text, text, [pin], None), "role": "eligibility_condition",
                "comparator": "none", "basis": "", "condition_group": "membership.requirements",
                "condition_logic": "single", "conditions": [text], "numeric_unit": "text", "scale": ""}}


def catalog():
    text = "Applicants must live in the service area. Applicants must retain a savings account."
    return {"_version": "test", "_schema_version": 2, "facts": [
        raw("Applicants must live in the service area.", "membership.area", 1, text),
        raw("Applicants must retain a savings account.", "membership.account", 2, text)]}, text


def answer(facts):
    store = FactStore(); store.add(SID, "2026-09-28", facts); store.finalize()
    return resolve(Query("value", "membership", "eligibility", (), None, False,
                         "What are the membership requirements?", frozenset(), "requirements"), store, R)


def test_derived_membership_survives_serde_and_detects_selection_loss():
    data, text = catalog()
    entries = parse_prose(data, R)
    facts = ProseBook(entries).facts(SID, SourcePages([source_page(SID, URL, text)]))
    restored = [fact_from_dict(json.loads(json.dumps(fact_to_dict(f)))) for f in facts]
    assert facts == restored and answer(restored).confident
    assert not complete_groups(restored[:1]) and not answer(restored[:1]).confident
    lowered = [restored[0], replace(restored[1], source=replace(restored[1].source, authority=-1))]
    assert not answer(lowered).confident


def test_missing_source_member_still_blocks_complete_requirements():
    data, text = catalog()
    # The first pin verifies a page that lacks the second source claim.
    data["facts"][0] = raw(data["facts"][0]["quote"], "membership.area", 1, data["facts"][0]["quote"])
    entries = parse_prose(data, R)
    facts = ProseBook(entries).facts(SID, SourcePages([source_page(SID, URL, data["facts"][0]["quote"])]))
    assert len(facts) == 1 and not answer(facts).confident


def test_declared_unknown_requirement_blocks_without_inventing_it():
    data, text = catalog()
    data["claim_groups"] = [{"entity": "membership", "attribute": "eligibility", "claim_set": "membership.requirements",
                            "crawls": [SID], "required_claim_ids": ["membership.unknown_approval"]}]
    facts = ProseBook(parse_prose(data, R)).facts(SID, SourcePages([source_page(SID, URL, text)]))
    assert len(facts) == 2 and not answer(facts).confident


def test_unannotated_high_authority_extractor_cannot_bypass_required_group():
    data, text = catalog()
    book = ProseBook(parse_prose(data, R))
    facts = book.facts(SID, SourcePages([source_page(SID, URL, text)]))
    unrelated = replace(facts[0], semantics=None, claim_groups=(), extractor="rules",
                        source=replace(facts[0].source, authority=10, quote="A different assertion."))
    bound = book.bind_groups(SID, facts + [unrelated])
    assert bound[-1].claim_groups and not answer(bound).confident


@pytest.mark.parametrize("question,requirements", [
    ("What are the membership requirements?", ("Any", "live or work", "immediate family member",
                                                "Rural Ideas Network", "$25", "open a savings account")),
    ("What are the Mortgage Rate Relief eligibility requirements?", ("new purchase", "at or below 80%",
              "Federal Housing Finance Agency", "Underserved Areas Data", "Additional eligibility", "approval")),
])
def test_installed_eligibility_answers_preserve_alternatives_and_mandatory_conditions(ks_full, question, requirements):
    result = ks_full.answer(question)
    assert result.confident and all(part in result.text for part in requirements)
    parsed = ks_full._parse(question, None)
    facts = ks_full.store.by_product_attr[SID][(parsed.product_id, "eligibility")]
    required = {claim_id for f in facts for group in f.claim_groups for claim_id in group.required_claim_ids}
    assert required
    for missing in sorted(required):
        survivors = [f for f in facts if all(group.claim_id != missing for group in f.claim_groups)]
        store = FactStore(); store.add(SID, "2026-09-28", survivors); store.finalize()
        assert not resolve(parsed, store, ks_full.registry).confident, missing
