"""A generic page mention must preserve the requested destination and named program."""
import pytest
from kb.question import parse
from kb.registry import Registry

R = Registry.load()


@pytest.mark.parametrize("question", [
    "What website is used to join Dupaco online?",
    "What's the website called where I can join?",
    "What's the website I'd use to join?",
    "What website am I supposed to use to join?",
    "What website can I use to become a member?",
])
def test_joining_destination_wins_over_generic_page_context(question):
    query = parse(question, None, R)
    assert (query.intent, query.product_id, query.attribute) == ("url", "membership", "url")


@pytest.mark.parametrize("question,expected", [
    ("Who qualifies for Home$tart?", ("value", "home_start", "eligibility")),
    ("Who qualifies for Mortgage Rate Relief?", ("value", "mortgage_rate_relief", "eligibility")),
    ("What is the website for auto loans?", ("url", "auto_loan", "url")),
    ("What is the website showing for the HELOC APR?", ("value", "heloc", "apr")),
    ("What phone number is on the website?", ("phone", "membership", "phone")),
    ("What is the website?", ("url", "website", "url")),
])
def test_joining_fallback_does_not_capture_named_products_or_other_intents(question, expected):
    query = parse(question, None, R)
    assert (query.intent, query.product_id, query.attribute) == expected
