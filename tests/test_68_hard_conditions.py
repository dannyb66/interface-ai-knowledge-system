"""Scope every conditional branch before allowing a confident fee answer."""
from dataclasses import replace
import pytest

from conftest import make_fact
from kb.conditions import CONDITION_VALUES, query_conditions, select_conditions, source_conditions, validate_conditions
from kb.question import Query, parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.store import FactStore
from kb.types import ClaimType


def query(text, pid="notary_services_fee"):
    return Query("value", pid, "fee", tuple(sorted(query_conditions(text).items())), None, False,
                 text, frozenset(), text)


@pytest.mark.parametrize("text,key,value", [
    ("I'm a member depositing my coins", "membership", "member"),
    ("I'm not a member", "membership", "non_member"),
    ("a non-member depositing coins", "deposit_disposition", "deposited"),
    ("I won't be depositing my coins", "deposit_disposition", "not_deposited"),
    ("I am not going to deposit the coins", "deposit_disposition", "not_deposited"),
    ("I don't use e-statements", "statement_delivery", "without_e_statements"),
    ("without e-statements", "statement_delivery", "without_e_statements"),
    ("no e-statements", "statement_delivery", "without_e_statements"),
    ("I never signed up for e-statements", "statement_delivery", "without_e_statements"),
    ("I signed up for e-statements", "statement_delivery", "e_statements"),
    ("after the first eight transactions", "usage_allowance", "after_eight_free"),
    ("within the eight free transactions", "usage_allowance", "within_eight_free"),
])
def test_explicit_condition_grammar(text, key, value):
    assert query_conditions(text)[key] == value


def test_coin_or_branches_require_only_their_own_sufficient_conditions():
    rows = [make_fact("coin", "fee", "Free", membership="member", deposit_disposition="deposited"),
            make_fact("coin", "fee", "5%", membership="non_member"),
            make_fact("coin", "fee", "5%", deposit_disposition="not_deposited")]
    for text in ("nonmember", "not a member", "member not depositing coins", "not depositing coins"):
        selected = select_conditions(rows, query(text))
        assert selected and {f.value_text for f in selected} == {"5%"}
    assert select_conditions(rows, query("member depositing coins")) == rows[:1]
    for text in ("member", "depositing coins", "coin counting", "member and nonmember"):
        assert not select_conditions(rows, query(text))


def test_condition_values_are_narrow_and_orthogonal():
    validate_conditions({"membership": "member", "deposit_disposition": "deposited"})
    with pytest.raises(ValueError):
        validate_conditions({"membership": "member_deposited"})
    assert query_conditions("member and non-member")["membership"] == "contradictory"


def test_legacy_schedule_scope_cannot_bypass_condition_guard():
    quals = source_conditions("Notary services", "$10 for non-members")
    fact = make_fact("notary_services_fee", "fee", "$10 for non-members", value=10, unit="usd",
                     claim=ClaimType.ASSERTION, **quals)
    store = FactStore(); store.add(fact.source.snapshot_id, "2026-09-28", [fact]); store.finalize()
    registry = Registry.load()
    assert resolve(query("nonmember"), store, registry).confident
    for text in ("member", "notary services cost"):
        assert not resolve(query(text), store, registry).confident
    parsed = parse("How much are notary services for a non-member?", None, registry)
    assert dict(parsed.slots)["membership"] == "non_member"


def test_legacy_billpay_and_usage_scope():
    assert source_conditions("Per bill (Free if signed up for e-statements)", "$0.50") == {
        "statement_delivery": "without_e_statements"}
    assert source_conditions("ATM withdrawal after 8 free", "$1") == {"usage_allowance": "after_eight_free"}


@pytest.mark.parametrize("text,key", [
    ("not currently a member", "membership"),
    ("not an active member", "membership"),
    ("not a non-member", "membership"),
    ("no longer a member", "membership"),
    ("I do not know whether I am a member", "membership"),
    ("I might be a member", "membership"),
    ("member status is unknown", "membership"),
    ("member or not", "membership"),
    ("a former member", "membership"),
    ("a lapsed member", "membership"),
    ("a prospective member", "membership"),
    ("an expired member", "membership"),
    ("a potential member", "membership"),
    ("a future member", "membership"),
    ("a hypothetical member", "membership"),
    ("I would be a member", "membership"),
    ("I used to be a member", "membership"),
    ("a would-be member", "membership"),
    ("an ex-member", "membership"),
    ("a member-to-be", "membership"),
    ("a member in the past", "membership"),
    ("a member of another credit union", "membership"),
    ("a member elsewhere", "membership"),
    ("a member of Costco", "membership"),
    ("a nonmember of Costco", "membership"),
    ("a member of another bank", "membership"),
    ("a member of the credit union called Riverbank", "membership"),
    ("a member of Riverbank", "membership"),
    ("a Riverbank member", "membership"),
    ("for Costco members", "membership"),
    ("a member of Dupaco or Riverbank", "membership"),
    ("not within the first eight free uses", "usage_allowance"),
    ("not after the first eight free uses", "usage_allowance"),
    ("maybe signed up for e-statements", "statement_delivery"),
    ("not actually enrolled in e-statements", "statement_delivery"),
    ("not sure if the coins will be deposited", "deposit_disposition"),
    ("non-debit card", "card"),
    ("not using a credit card", "card"),
])
def test_unresolved_conditions_never_become_affirmative_scope(text, key):
    assert query_conditions(text)[key] == "contradictory"
    fact = make_fact("example_fee", "fee", "$5", **{key: sorted(CONDITION_VALUES[key])[0]})
    assert not select_conditions([fact], query(text))


def test_known_negative_membership_does_not_negate_deposit_in_the_same_clause():
    conditions = query_conditions("not a member depositing coins")
    assert conditions == {"membership": "non_member", "deposit_disposition": "deposited"}


@pytest.mark.parametrize("condition", [
    "I am not currently a member and the coins are deposited",
    "I do not know whether I am a member and the coins are deposited",
    "I might be a member and the coins are deposited",
    "I am a former member depositing coins",
    "I am a lapsed member depositing coins",
    "I am a prospective member depositing coins",
    "I am a potential member depositing coins",
    "I am a future member depositing coins",
    "I would be a member depositing coins",
    "I used to be a member depositing coins",
    "I am a would-be member depositing coins",
    "I am an ex-member depositing coins",
    "I am a member-to-be depositing coins",
    "I was a member in the past depositing coins",
    "I am a member of another credit union depositing coins",
    "I am a member elsewhere depositing coins",
    "I am a member of Costco depositing coins",
    "I am a nonmember of Costco depositing coins",
    "I am a member of another bank depositing coins",
    "I am a Riverbank member depositing coins",
])
def test_unknown_membership_cannot_receive_the_installed_free_coin_price(ks_full, condition):
    answer = ks_full.answer("What is the Self Service coin counting fee? " + condition)
    assert not answer.confident and "Free" not in answer.text and "5%" not in answer.text


def test_negated_allowance_cannot_receive_the_installed_atm_charge(ks_full):
    answer = ks_full.answer("What is the non-Dupaco ATM fee not after the first eight free transactions?")
    assert not answer.confident and "$" not in answer.text


@pytest.mark.parametrize("condition", ["a current member", "an active member", "a member of Dupaco",
                                      "a Dupaco member", "a member of the credit union", "a long-time member"])
def test_current_serving_membership_remains_positive(ks_full, condition):
    answer = ks_full.answer("What is the Self Service coin counting fee for " + condition + " depositing coins?")
    assert answer.confident and "Free" in answer.text and "deposited" in answer.text
