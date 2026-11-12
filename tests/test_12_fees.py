import pytest
from kb.extract_fees import priced_rows


def test_fee_facts_in_every_crawl(ks_full):
    counts = {"01_2026-05-12_baseline": 53, "02_2026-05-19_recrawl": 53,
              "03_2026-06-09_recrawl": 53, "04_2026-08-27_rebaseline": 51,
              "05_2026-09-28_latest": 54}
    for sid, _ in ks_full.store.snapshots():
        store = ks_full.store.by_product_attr[sid]
        assert {f.value_text for f in store[("stop_payment_fee", "fee")]} == {"$30.00 per item"}
        assert len({pid for pid, attr in store if attr == "fee"}) == counts[sid]
        for (pid, attr), fs in store.items():
            if attr == "fee":
                assert all(f.effective_date == "2025-02-17" for f in fs)
                for fact in fs:
                    if fact.semantics is None:
                        assert fact.unit == "usd" and fact.value is not None
                    elif fact.unit in ("free", "text"):
                        assert fact.value is None
                    else:
                        assert fact.unit in ("usd", "percent") and fact.value is not None


@pytest.mark.parametrize("question,token", [
    ("What's the fee for a stop payment?", "$30"),
    ("How much does a domestic wire transfer cost?", "$25"),
    ("What does Dupaco charge for an overdraft?", "$30"),
    ("What's the rush fee for a debit card?", "$50"),
    ("What is the par value of a share at Dupaco?", "$25"),
    ("What is the fee for an incoming wire?", "$10"),
    ("How much does an international wire cost?", "$55"),
])
def test_fee_answers(ks_full, question, token):
    answer = ks_full.answer(question)
    assert answer.confident and token in answer.text


@pytest.mark.parametrize("question", ["What is the fee for a cashier's check?", "What is the fee for a lost debit card?"])
def test_unknown_fee_refuses(ks_full, question):
    answer = ks_full.answer(question)
    assert not answer.confident and "$" not in answer.text


@pytest.mark.parametrize("question", ["How do I stop payment?", "What is the URL for the ATM fee?"])
def test_fee_amount_does_not_answer_another_intent(ks_full, question):
    assert not ks_full.answer(question).confident


def test_fee_rows_do_not_leak_into_rates(ks_full):
    assert "$30" not in ks_full.answer("What is the Share Savings APY?").text
    assert ks_full.answer("What's the URL for Dupaco's branch and ATM locator?").text == "Branch: https://www.dupaco.com/contact"


def test_each_priced_product_has_an_unambiguous_name(ks_full):
    registry = ks_full.registry
    for pid in sorted(set(registry.aliases().values())):
        if registry.family(pid) == "fees":
            question = "What is the fee for {}?".format(registry.display_name(pid))
            query = ks_full._parse(question, None)
            assert (query.product_id, query.attribute) == (pid, "fee"), pid
            if pid == "notary_services_fee":
                assert not ks_full.answer(question).confident  # the schedule prices nonmembers only
                assert ks_full.answer(question + " For a nonmember.").confident
            elif pid == "signature_guarantee_fee":
                assert not ks_full.answer(question).confident
                assert ks_full.answer(question + " For a member.").confident
            elif pid == "self_service_coin_counting_fee":
                assert not ks_full.answer(question).confident
                assert ks_full.answer(question + " For a member with the coins deposited.").confident
            elif pid == "per_bill_paid_or_attempted_to_pay_free_if_signed_up_for_e_statements_fee":
                # A label containing the free condition cannot claim the extracted numeric price.
                answer = ks_full.answer(question)
                assert not answer.confident or "Free" in answer.text
            else:
                assert ks_full.answer(question).confident, pid


def test_installed_coin_fee_branches_keep_all_conditions_and_the_scoped_tax_note(ks_full):
    question = "What is the Self Service coin counting fee"
    free = ks_full.answer(question + " for a member with the coins deposited?")
    assert free.confident and "Free" in free.text and "for members" in free.text and "coins deposited" in free.text
    assert "5%" not in free.text and "tax" not in free.text.lower()
    for condition in ("for a non-member", "for a member not depositing coins", "when not depositing coins"):
        charged = ks_full.answer(question + " " + condition + "?")
        assert charged.confident and "5%" in charged.text and "Sales tax may apply" in charged.text
        assert "*" not in charged.text
    for condition in ("", "for a member", "with the coins deposited"):
        assert not ks_full.answer(question + " " + condition + "?").confident
    assert not ks_full.answer(question + " for a non-member?", "2026-08-27").confident  # tax note alone


def test_installed_billpay_prices_require_explicit_statement_delivery(ks_full):
    question = "What is the fee per bill paid or attempted to pay"
    free = ks_full.answer(question + " with e-statements?")
    charged = ks_full.answer(question + " without e-statements?")
    assert free.confident and "Free" in free.text and "tax" not in free.text.lower()
    assert charged.confident and "$0.50" in charged.text and "without e-statements" in charged.text
    assert "Sales tax may apply" in charged.text and "*" not in charged.text
    assert not ks_full.answer(question + "?").confident


def test_installed_debit_foreign_fee_cannot_serve_an_unknown_or_credit_card(ks_full):
    question = "What is the Debit Card Service Charges Foreign transaction fee"
    debit = ks_full.answer(question + "?")
    assert debit.confident and "1%" in debit.text and "for debit cards" in debit.text
    for text in ("What is the foreign transaction fee?", "What is the Visa foreign transaction fee?",
                 "What is the credit card foreign transaction fee?", question + " for a credit card?"):
        assert not ks_full.answer(text).confident


def test_fee_footnotes_and_wrapped_labels():
    rows = list(priced_rows("|Stop payment|$30.00* per item|\n|Overdraft|$30.00 per item *Extra $5.00 detail|\nForeign currency exchange fee\n(includes Canadian checks) $35.00\n_Official check $5.00_ each\nThe par value of a share in the credit union is $25.00."))
    assert [(label, value) for _, label, value, _ in rows] == [
        ("Stop payment", "$30.00 per item"), ("Overdraft", "$30.00 per item"),
        ("Foreign currency exchange fee (includes Canadian checks)", "$35.00"),
        ("Official check", "$5.00 each"), ("Share par value", "$25.00")]


@pytest.mark.parametrize("question", [
    "What is the fee for a domestic wire recall?", "What does it cost to recall an international wire?",
    "What is the official check cancellation fee?", "What is the fee for money order replacement?",
    "What is the fee to reissue an official check?", "How much is a wire transfer reversal?",
    "What is the incoming outgoing wire fee?",
])
def test_unsupported_fee_operations_do_not_borrow_a_base_service(ks_full, question):
    answer = ks_full.answer(question)
    assert not answer.confident and "$" not in answer.text


@pytest.mark.parametrize("question", [
    "What is the fee for an incoming international wire transfer?",
    "What is the charge for receiving a domestic wire?",
    "How much is an inbound foreign wire?", "How much for an incoming international wire?",
])
def test_wire_direction_precedes_origin(ks_full, question):
    answer = ks_full.answer(question)
    assert answer.confident and "$10.00" in answer.text and "$55" not in answer.text and "$25" not in answer.text
