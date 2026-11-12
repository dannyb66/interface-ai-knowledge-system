"""A cash advance cannot borrow the separately published purchase APR."""
import pytest

from kb.question import parse
from kb.registry import Registry

R = Registry.load()


@pytest.mark.parametrize('question', [
    'What is the APR on a Visa cash advance?',
    'What is the cash advance APR on a Visa?',
    'What is the interest rate for a cash advance on my Platinum Visa?',
    'On a Visa cash advance, do I pay $10 or 3%, and how are finance charges treated?',
    'What are the fees for a Platinum Visa cash-advance?',
])
def test_all_word_orders_preserve_unpublished_operation_scope(ks_full, question):
    q = parse(question, None, R)
    assert q.attribute == 'cash_advance' and q.explicit_attribute
    answer = ks_full.answer(question)
    assert not answer.confident and not answer.sources and not answer.conflict_note
    assert '12.50' not in answer.text and '13.00' not in answer.text


def test_purchase_apr_positive_control_is_unchanged(ks_full):
    answer = ks_full.answer('What is the purchase APR on a Platinum Visa?')
    assert answer.confident and '12.50%' in answer.text
