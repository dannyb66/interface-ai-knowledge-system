"""New source topics cannot shadow existing fee, branch or recognition scopes."""
from dataclasses import replace

import pytest

from kb.routing import recover
from kb.resolve import resolve


@pytest.mark.parametrize("question", ["What recognition has Dupaco received from Forbes?",
    "How many times has Forbes named Dupaco a top credit union?", "Has Forbes recognized Dupaco?"])
def test_audited_historical_entities_cannot_supply_forbes_claims(ks_full, question):
    unrelated = {"des_moines_register_recognition", "sp_global_credit_union_ranking", "thank_use_patronage"}
    current = ks_full.store.by_product_attr["05_2026-09-28_latest"]
    assert all(any("2021" in f.value_text for (pid, _), facts in current.items() if pid == name for f in facts)
               for name in unrelated)
    original = ks_full._parse(question, None)
    for enabled in (False, True):
        config = replace(ks_full.config, lexical_routing=enabled, unknown_topic_routing=enabled)
        routed = recover(original, ks_full._routing_index, ks_full.registry, config)
        assert routed == original and routed.product_id == "forbes_recognition"
        plan = resolve(routed, ks_full.store, ks_full.registry)
        assert plan.confident and plan.facts and {f.product_id for f in plan.facts} == {"forbes_recognition"}
        assert all("2021" not in f.value_text for f in plan.facts)
    answer = ks_full.answer(question)
    assert answer.confident and "fifth time" in answer.text and "2021" not in answer.text


@pytest.mark.parametrize("question", ["What is the fee for Notary services? For a nonmember.",
    "What is the Self Service coin counting fee for a non-member?"])
def test_nonmember_fee_question_is_not_a_compound_prose_request(ks_full, question):
    query = ks_full._parse(question, None)
    assert query.attribute == "fee" and not query.prose_scope_error and not query.requested_prose_attributes
    assert dict(query.slots)["membership"] == "non_member" and ks_full.answer(question).confident


@pytest.mark.parametrize("question", ["When did the Asbury branch close?", "Is the Asbury branch closed?",
                                     "What is the closing date for the Asbury branch?"])
def test_notice_topic_does_not_shadow_branch_closure(ks_full, question):
    query = ks_full._parse(question, None)
    assert query.product_id == "branch" and dict(query.slots)["branch_name"] == "asbury"
    answer = ks_full.answer(question)
    assert answer.confident and "closed on Oct. 1, 2024" in answer.text
