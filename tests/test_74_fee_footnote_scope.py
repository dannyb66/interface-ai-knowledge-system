"""A stripped footnote marker never discards a condition or borrows another page's note."""
from dataclasses import replace

from kb.claim_semantics import ClaimSemantics, semantics_survive
from kb.conditions import query_conditions, select_conditions
from kb.fee_semantics import presentation_statement, reviewed_duplicates
from kb.question import Query
from conftest import make_fact


def fee(text, unit="usd", condition="non_member"):
    fact = make_fact("coin_fee", "fee", text, unit=unit, membership=condition)
    annotation = ClaimSemantics(1, "example.fee", "0" * 64, "fee", "none", "", "example.schedule",
                                "single", (), unit, "")
    return replace(fact, semantics=annotation, source=replace(fact.source, content_sha256="a" * 64))


def test_same_source_and_scope_tax_companion_preserves_full_statement():
    price, note = fee("Coins $5* for non-members."), fee("* Sales tax may apply.", "text")
    rendered = "Coins, for non-members: Coins $5 for non-members. Sales tax may apply."
    assert semantics_survive(rendered, [price, note])
    assert not semantics_survive("Coins $5 for non-members.", [price, note])
    assert not semantics_survive(rendered, [price])


def test_free_branch_must_print_the_deposit_condition_after_selection():
    free = fee("Free for members", "free", "member")
    qualifiers = (("deposit_disposition", "deposited"), ("membership", "member"))
    free = replace(free, qualifiers=qualifiers)
    assert semantics_survive("Coin service, for members; with the coins deposited: Free for members.", [free])
    assert not semantics_survive("Coin service, for members: Free for members.", [free])


def test_other_raw_variant_or_branch_cannot_lend_a_tax_footnote():
    price, note = fee("Coins $5* for non-members."), fee("* Sales tax may apply.", "text")
    for invalid in (replace(note, source=replace(note.source, content_sha256="b" * 64)),
                    fee("* Sales tax may apply.", "text", "member")):
        assert presentation_statement(price, [price, invalid]) == price.value_text
        assert not semantics_survive("Coins $5 for non-members. Sales tax may apply.", [price, invalid])


def test_a_tax_note_cannot_answer_without_the_scoped_price():
    note = fee("* Sales tax may apply.", "text")
    q = Query("value", "coin_fee", "fee", (("membership", "non_member"),), None, False, "nonmember fee?", frozenset(), "q")
    assert not select_conditions([note], q)


def test_visa_is_a_brand_not_an_unconditional_credit_card_class():
    assert query_conditions("Visa debit card")["card"] == "debit"
    assert "card" not in query_conditions("Visa foreign fee")
    assert query_conditions("debit or credit card")["card"] == "contradictory"


def test_only_exact_verified_fee_duplicates_are_shadowed():
    candidate = replace(fee("Coins $5* for non-members."), value=5, extractor="curated")
    candidate = replace(candidate, source=replace(candidate.source, quote="Coins $5* for non-members."))
    old = replace(candidate, semantics=None, extractor="rules", value_text="$5 for non-members")
    assert reviewed_duplicates([old, candidate]) == [candidate]
    assert reviewed_duplicates([old]) == [old]
    mutations = [replace(old, effective_date="2027-01-01"), replace(old, value=6), replace(old, unit="percent"),
                 replace(old, key=("another", "fee", old.qualifiers)),
                 replace(old, source=replace(old.source, content_sha256="b" * 64)),
                 replace(old, source=replace(old.source, quote="An unrelated row also costs $5."))]
    for other in mutations:
        assert reviewed_duplicates([other, candidate]) == [other, candidate]
