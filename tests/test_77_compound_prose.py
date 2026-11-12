"""A two-scope request must not silently become one partial prose answer."""
from dataclasses import asdict, replace
import json

import pytest

from kb.claim_semantics import SourcePin, semantic_revision
from kb.compound_prose import ATTRIBUTES, complete_render
from kb.compose import render
from kb.config import Config
from kb.prose_facts import ProseBook, parse_prose
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.source_pages import SourcePages, content_digest, source_page
from kb.store import FactStore
from kb.system import KnowledgeSystem
from kb.types import fact_from_dict, fact_to_dict

SID = "05_2026-09-28_latest"
DAY = "2026-09-28"
R = Registry.load()
ASK = "Is membership required for business insurance, and which states license the agency?"


def catalog():
    texts = (("eligibility", "Membership is not required to use this service."),
             ("eligibility", "Applicants must complete the application."),
             ("description", "The agency is licensed in Iowa and Illinois."))
    entries, pages = [], []
    for item, (attr, text) in enumerate(texts, 1):
        url = "https://example.test/source-" + str(item)
        pin = SourcePin(SID, url, content_digest(text))
        entries.append({"canonical_urls": [url], "crawls": [SID], "quote": text,
            "product_id": "business_insurance", "attribute": attr, "qualifiers": {"item": item},
            "value": None, "value_text": text, "unit": "text", "claim_type": "assertion",
            "published_date": None, "event_date": None, "effective_date": None, "extractor": "curated",
            "source_pins": [asdict(pin)], "semantics": {"version": 1, "claim_id": "example." + str(item),
                "revision": semantic_revision(text, text, [pin], None), "role": "eligibility_condition" if attr == "eligibility" else "description",
                "comparator": "none", "basis": "", "condition_group": "example.requirements" if attr == "eligibility" else "",
                "condition_logic": "single", "conditions": [text], "numeric_unit": "text", "scale": ""}})
        pages.append(source_page(SID, url, text))
    book = ProseBook(parse_prose({"_version": "test", "_schema_version": 2, "facts": entries}, R))
    return book, pages


def store(rows):
    result = FactStore(); result.add(SID, DAY, rows); result.finalize()
    return result


def facts():
    book, pages = catalog()
    return book.facts(SID, SourcePages(pages))


@pytest.mark.parametrize("text", [
    ASK,
    "Which states license business insurance, and is membership required?",
    "Who can use the Financial Wellness program, and how is it delivered?",
    "How is the Financial Wellness program delivered, and who can participate?",
    "Describe the services of business insurance and its eligibility requirements.",
    "Must I belong to Dupaco to use business insurance, and which states license the agency?",
    "Is Dupaco membership required for business insurance, and how does the service work?",
    "I am comparing business insurance agencies. Does Dupaco require membership, and what geographic licensing limits does it state?",
])
def test_both_orders_and_general_membership_delivery_grammar(text):
    query = parse(text, DAY, R)
    assert query.requested_prose_attributes == ATTRIBUTES and not query.prose_scope_error


def test_both_independently_resolved_scopes_keep_labels_and_source_evidence():
    rows = [fact_from_dict(json.loads(json.dumps(fact_to_dict(f)))) for f in facts()]
    q = parse(ASK, DAY, R)
    plan = resolve(q, store(rows), R)
    result = render(plan)
    assert result.confident and not result.text.startswith(("Yes.", "No."))
    assert " eligibility:" in result.text and " service information:" in result.text
    assert all(f.value_text in result.text for f in rows)
    assert set(s.url for s in result.sources) == {f.source.url for f in rows}
    assert not complete_render(result.text.replace(rows[-1].value_text, ""), plan)
    assert plan.as_of == DAY and plan.question == q.raw_span


@pytest.mark.parametrize("loss", ["description", "eligibility", "required_member", "authority", "date", "source"])
def test_any_unsupported_or_incomplete_arm_refuses_the_whole_request(loss):
    rows = facts()
    if loss in ("description", "eligibility"):
        rows = [f for f in rows if f.attribute != loss]
    elif loss == "required_member":
        rows = rows[1:]
    elif loss == "authority":
        rows[1] = replace(rows[1], source=replace(rows[1].source, authority=-1))
    elif loss == "date":
        rows[-1] = replace(rows[-1], effective_date="2026-10-01")
    else:
        book, pages = catalog()
        rows = book.facts(SID, SourcePages(pages[:-1]))
    assert not render(resolve(parse(ASK, DAY, R), store(rows), R)).confident


def test_unpublished_requested_attribute_cannot_be_erased():
    registry = Registry.load()
    registry._published["business_insurance"] = frozenset({"description"})
    q = parse(ASK, DAY, registry)
    assert q.requested_prose_attributes == ATTRIBUTES
    assert not resolve(q, store(facts()), registry).confident


@pytest.mark.parametrize("text", [
    "What are business insurance eligibility requirements and the APR?",
    "What are business insurance membership requirements and the fee?",
    "Who can use business insurance and Financial Wellness, and how are they delivered?",
    "Who can use business insurance and the Financial Wellness program, and how is each delivered?",
    "Who can use business insurance and Zephyrix services, and how is each delivered?",
    "How does business insurance operate?",
    "Who can use business insurance?",
])
def test_numeric_multi_entity_and_single_scope_questions_do_not_enter_this_path(text):
    assert not parse(text, DAY, R).requested_prose_attributes


def test_personal_eligibility_does_not_become_a_yes_verdict():
    q = parse("Am I eligible for business insurance, and which states license the agency?", DAY, R)
    assert q.requested_prose_attributes == ATTRIBUTES
    assert not render(resolve(q, store(facts()), R)).confident


@pytest.mark.parametrize("text", [
    "Who can use business insurance, and what services does Zephyrix provide?",
    "Which states license business insurance, and who can use Zephyrix?",
    "Who can use business insurance and Zephyrix services, and how is each delivered?",
    "Who can use business insurance; what services does Zephyrix offer?",
    "Who can use business insurance, and how does Zephyrix work?",
    "Must I belong to Dupaco to use business insurance, and which states license Zephyrix?",
    "Must I belong to Zephyrix to use business insurance, and which states license the agency?",
    "I am comparing business insurance agencies. Does Zephyrix require membership, and which states license it?",
])
def test_unknown_second_subject_cannot_borrow_the_recognized_entity(text):
    query = parse(text, DAY, R)
    assert query.prose_scope_error
    assert not render(resolve(query, store(facts()), R)).confident


@pytest.mark.parametrize("text", [
    "Can I qualify for business insurance, and which states license the agency?",
    "Could we qualify for business insurance, and which states license the agency?",
])
def test_compound_rephrasing_cannot_bypass_personal_eligibility_guard(text):
    assert not render(resolve(parse(text, DAY, R), store(facts()), R)).confident


def test_original_queries_have_distinct_cache_entries_and_explain_parity():
    ks = KnowledgeSystem(Config.from_env())
    ks.store = store(facts()); ks._warm_up()
    questions = (ASK, "Which states license business insurance, and is membership required?")
    for text in questions:
        q = ks._parse(text, DAY)
        result = ks.answer(text, DAY)
        assert result.confident and q in ks._answers
        assert ks.explain(text, DAY)["answer"] == result.text
    assert len(ks._answers) == 2
    q = ks._parse(questions[0], DAY)
    assert replace(q, requested_prose_attributes=()) != q
    assert ks.answer("Who can use business insurance?", DAY).text != ks.answer(ASK, DAY).text


@pytest.mark.parametrize("text,parts", [
    ("Is membership required for business insurance, and which states license the agency?", ("member", "Iowa", "Arizona")),
    ("Who can use the Financial Wellness program, and how is it delivered?", ("all employees", "coaching")),
])
def test_installed_source_scopes_remain_distinct(ks_full, text, parts):
    result = ks_full.answer(text, DAY)
    assert result.confident and all(p.lower() in result.text.lower() for p in parts)
    assert " eligibility:" in result.text and " service information:" in result.text
