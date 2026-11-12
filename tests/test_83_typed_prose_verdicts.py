"""Typed evidence preserves its predicate and polarity without a word-subset verdict."""
import pytest

from conftest import single_plan
from kb.compose import render
from kb.diagnostics import answer_dict
from test_66_claim_semantics import entry, fact_for


@pytest.mark.parametrize("statement,question", [
    ("Example does not provide account protection.", "Does Example provide account protection?"),
    ("Example isn't backed by a government.", "Is Example backed by a government?"),
    ("Example isn’t backed by a government.", "Is Example backed by a government?"),
    ("Example protects a loan.", "Is Example a loan?"),
    ("Example provides protection only after approval.", "Does Example provide protection?"),
    ("Example provides account protection.", "Does Example provide account protection?"),
])
def test_typed_description_cannot_entail_a_verdict_from_shared_words(statement, question):
    fact = fact_for(entry(statement, "text", None, "description", "description", "home_start"))
    answer = render(single_plan("yes_no", fact, question=question, strict_numbers=True))
    assert answer.confident and statement in answer.text
    assert not answer.text.startswith(("Yes.", "No."))


@pytest.mark.parametrize("question,product,negative_claim", [
    ("Is payment protection required?", "payment_protection", "payment_protection.description.2"),
    ("Is payment protection a loan?", "payment_protection", "payment_protection.description.2"),
    ("Is cryptocurrency backed by a government?", "cryptocurrency", "cryptocurrency.description.2"),
])
def test_installed_negative_description_keeps_its_statement_without_false_yes(
        ks_full, question, product, negative_claim):
    facts = ks_full.store.by_product_attr["05_2026-09-28_latest"][(product, "description")]
    fact = next(f for f in facts if f.semantics and f.semantics.claim_id == negative_claim)
    statement = fact.value_text.lower().replace("’", "'")
    assert "not" in statement or "n't" in statement
    answer = ks_full.answer(question)
    assert answer.confident and fact.value_text in answer.text
    assert not answer.text.startswith(("Yes.", "No."))
    detail = ks_full.explain(question)
    assert answer_dict(answer) == {"text": detail["answer"], "sources": detail["sources"],
                                  "confident": detail["confident"], "conflict_note": detail["conflict_note"]}
    assert ks_full.answer(question) == answer
