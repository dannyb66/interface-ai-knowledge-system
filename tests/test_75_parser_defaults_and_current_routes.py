"""Recover current, source-supported scopes without erasing explicit constraints."""
from dataclasses import replace
from pathlib import Path

import pytest

from kb.config import Config
from kb.lexical_index import Route
from kb.question import Query, parse
from kb.registry import Registry
from kb.routing import apply_route, recover
from test_73_guarded_source_routing import config, index, query, registry

R = Registry.load()


def test_exact_serving_date_is_retained_but_other_dates_remain_blocked():
    catalog = index()
    original = replace(query(), as_of="2026-09-28")
    routed = recover(original, catalog, registry(), config())
    assert routed.product_id == "storm_claim"
    assert routed.as_of == original.as_of and routed.raw_span == original.raw_span
    for day in ("2026-09-27", "2026-09-29", "2026-05-12"):
        old = replace(original, as_of=day)
        assert recover(old, catalog, registry(), config()) == old
        with pytest.raises(ValueError):
            apply_route(old, Route("storm_claim", "description", 1, 2, 4), catalog.latest_day)


def test_informational_default_can_change_but_explicit_rate_cannot():
    catalog = index()
    original = replace(query("Explain the storm insurance claim process"), product_id="storm_claim",
                       product_ids=("storm_claim",), attribute="apr", generic_rate=True)
    routed = recover(original, catalog, registry(), config())
    assert routed.attribute == "description" and not routed.generic_rate
    assert routed.raw_span == original.raw_span
    explicit = replace(original, explicit_attribute=True)
    assert recover(explicit, catalog, registry(), config()) == explicit
    with pytest.raises(ValueError):
        apply_route(explicit, Route("storm_claim", "description", 1, 2, 4))


def test_a_preserved_explicit_attribute_is_not_an_override_permission():
    original = replace(query("What are storm insurance claim requirements?"), attribute="eligibility", explicit_attribute=True)
    assert recover(original, index(), registry(), config()) == original  # description-only target cannot satisfy it
    with pytest.raises(ValueError):
        apply_route(original, Route("storm_claim", "description", 1, 2, 4))


@pytest.mark.parametrize("text", [
    "What is a useful social account checkup routine?",
    "Tell me about a regular password review routine.",
    "How often do you recommend checking privacy settings?",
    "Why should I start by checking my security settings?",
])
def test_actions_and_routines_do_not_name_checking_accounts_or_routing_numbers(text):
    parsed = parse(text, None, R)
    assert parsed.product_id not in ("first_rate_checking", "membership")
    assert parsed.attribute != "routing_number"


def test_actual_account_and_routing_requests_are_preserved():
    assert parse("What is the checking account APY?", None, R).product_id == "first_rate_checking"
    assert parse("What is the routing number?", None, R).attribute == "routing_number"
    assert parse("Can you repeat the routng number?", None, R).attribute == "routing_number"


def test_phone_object_in_device_procedure_is_not_a_request_for_the_general_number():
    for text in ("How should I handle a lost phone containing my mobile wallet?",
                 "What should I do if my phone containing a mobile wallet is stolen?"):
        parsed = parse(text, None, R)
        assert (parsed.product_id, parsed.attribute, parsed.intent) == ("mobile_wallet", "description", "how_to")
    assert parse("What phone number should I call for help?", None, R).attribute == "phone"


def test_named_program_outranks_incidental_employee_count_nouns():
    for text in ("Which employees can use the Financial Wellness program?",
                 "Who can access the Financial Wellness program?"):
        parsed = parse(text, None, R)
        assert (parsed.product_id, parsed.attribute) == ("employee_financial_wellness", "eligibility")
    assert parse("How many employees does Dupaco have?", None, R).product_id == "employee_count"


def test_present_process_is_not_historical_rate_change():
    parsed = parse("What happens to a business certificate at maturity?", None, R)
    assert (parsed.intent, parsed.attribute) == ("value", "description")
    assert parse("What happened to the certificate APY?", None, R).intent == "change"


def test_named_member_story_cannot_borrow_current_generic_product_facts():
    for text in ("In an earlier member story, how did someone manage to buy a car?",
                 "What happened to the family's savings in the member story?"):
        parsed = parse(text, None, R)
        assert parsed.product_id is None and parsed.route_blocked
    assert parse("What is the auto loan APR?", None, R).product_id == "auto_loan"
