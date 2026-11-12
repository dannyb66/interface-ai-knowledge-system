from dataclasses import replace

import pytest

from conftest import make_fact, single_plan
from kb.compose import render
from kb.question import parse
from kb.registry import Registry
from scoring import score_item

R = Registry.load()


def test_prose_public_answers(ks_full, public_items):
    for item in public_items:
        if item["id"] in ("dup-081", "dup-087", "dup-094", "dup-101", "dup-031", "dup-082", "dup-060"):
            answer = ks_full.answer(item["question"], item.get("as_of"))
            assert score_item(item, answer)["score"] == 1, (item["id"], answer.text)


def test_membership_eligibility_item_order_and_historical_crawl(ks_full):
    answer = ks_full.answer("Who is eligible to become a Dupaco member?")
    required = ("Any", "live or work within our charter area", "immediate family member who's a member",
                "Rural Ideas Network", "open a savings account with $25 or more", "keep at least $25",
                "Iowa, Illinois and Wisconsin")
    assert answer.confident and all(text in answer.text for text in required)
    assert [answer.text.index(text) for text in required] == sorted(answer.text.index(text) for text in required)
    old = ks_full.answer("Who was eligible to join Dupaco in May 2026?")
    assert old.confident and "or have an immediate family member who's a member." in old.text
    assert "open a savings account with $25 or more" in old.text and "keep at least $25" in old.text
    assert "Rural Ideas Network" not in old.text


@pytest.mark.parametrize("question", [
    "What recognition has Dupaco received from Forbes?", "Has Forbes recognized Dupaco?",
    "What has Forbes said about Dupaco?", "Did Dupaco get any Forbes awards?",
    "How many times has Forbes named Dupaco a top credit union?",
])
def test_forbes_answers_use_latest_publication(ks_full, question):
    answer = ks_full.answer(question)
    assert answer.confident and "fifth time" in answer.text and "fourth" not in answer.text
    if question.startswith(("Has", "Did")):
        assert answer.text.startswith("Yes.")


def test_description_without_fact_refuses(ks_full):
    latest = ks_full.store.by_product_attr["05_2026-09-28_latest"]
    bare = sorted(p for p in set(R.aliases().values()) if "description" in R.published(p) and not latest.get((p, "description")))
    for pid in bare:
        answer = ks_full.answer("What is the {}?".format(R.display_name(pid)))
        assert not answer.confident and not any(ch.isdigit() for ch in answer.text), pid
    assert not ks_full.answer("What is the Jump Start savings account?").confident


def test_how_to_keeps_every_attribute():
    link = make_fact("membership", "url", "https://join.dupaco.com/", unit="text")
    eligibility = make_fact("membership", "eligibility", "You live or work within our charter area.", extractor="curated", unit="text")
    plan = replace(single_plan("how_to", link), facts=(link, eligibility), strict_numbers=True)
    assert render(plan).text == "You can do that online at https://join.dupaco.com/\nMembership: You live or work within our charter area."


@pytest.mark.parametrize("question,intent,pid,attr", [
    ("What recognition has Dupaco received from Forbes?", "value", "forbes_recognition", "description"),
    ("Has Forbes recognized Dupaco?", "yes_no", "forbes_recognition", "description"),
    ("How many times has Forbes named Dupaco a top credit union?", "count", "forbes_recognition", "description"),
    ("How many credit unions participate in shared branching?", "count", "shared_branching", "count"),
    ("Who can join Dupaco?", "value", "membership", "eligibility"),
    ("Am I eligible for Dupaco membership?", "value", "membership", "eligibility"),
    ("What are the requirements to become a member?", "value", "membership", "eligibility"),
])
def test_prose_routes(question, intent, pid, attr):
    query = parse(question, None, R)
    assert (query.intent, query.product_id, query.attribute) == (intent, pid, attr)


@pytest.mark.parametrize("question", [
    "Does the Home$tart program provide $20,000 in assistance?", "Is the Home$tart grant $25,000?",
    "Has Forbes recognized Dupaco 4 times?", "Has Forbes recognized Dupaco four times?",
    "Has Forbes recognized Dupaco for the fourth time?",
    "Is this the fourth Forbes recognition?", "Is this the 4th Forbes recognition?",
    "Does shared branching have 999999 participating credit unions?",
])
def test_prose_verdict_rejects_contradicted_number_or_ordinal(ks_full, question):
    answer = ks_full.answer(question)
    assert answer.confident and answer.text.startswith("No. "), answer.text


def test_prose_verdict_keeps_supported_claims_and_avoids_unproved_semantics(ks_full):
    for question in ("Does the Home$tart program provide $15,000 in assistance?", "Has Forbes recognized Dupaco five times?",
                     "Is this the fifth Forbes recognition?", "Is this the 5th Forbes recognition?"):
        assert ks_full.answer(question).text.startswith("Yes. ")
    for question in ("Does the Home$tart program provide a free car?", "Has Forbes never recognized Dupaco?",
                     "Has Dupaco received four Forbes awards?",
                     "Is the Home$tart grant 20%?",
                     "Has Forbes recognized Dupaco 999999?", "Has Forbes recognized Dupaco nineteen?"):
        answer = ks_full.answer(question)
        assert answer.confident and not answer.text.startswith("Yes. "), (question, answer.text)


def test_prose_verdict_uses_historical_ordinal_evidence(ks_full):
    for ordinal, verdict in (("fourth", "Yes."), ("fifth", "No.")):
        answer = ks_full.answer("Is this the {} Forbes recognition?".format(ordinal), "2023-12-31")
        assert answer.confident and answer.text.startswith(verdict) and "fourth time" in answer.text, answer.text


@pytest.mark.parametrize("product,pid", [("Home$tart", "home_start"), ("Mortgage Rate Relief", "mortgage_rate_relief"), ("membership", "membership")])
def test_qualifies_preserves_the_named_program(ks_full, product, pid):
    question = "Who qualifies for {}?".format(product)
    query = ks_full._parse(question, None)
    assert (query.product_id, query.attribute) == (pid, "eligibility")
    assert ks_full.answer(question).confident


def test_business_you_name_it_account_alias_keeps_business_scope(ks_full):
    question = "If I deposit $1,200 into my business You Name It account, what yield applies?"
    query = ks_full._parse(question, None)
    assert query.product_id == "business_you_name_it_savings"
    assert "0.10%" in ks_full.answer(question).text
