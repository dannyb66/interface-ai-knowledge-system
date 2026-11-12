"""Informational predicates cannot turn into scalar financial requests or erase numbers."""
import pytest

from kb.question import parse
from kb.registry import Registry

R = Registry.load()
DAY = '2026-09-28'
CASES = [
    ('Who was elected in the board election and how long were their terms?', 'dupaco_board_elections', 'three-year'),
    ('How does life insurance compare term insurance and whole life?', 'life_insurance', 'term'),
    ('How do whole and term policies differ in the life insurance article?', 'life_insurance', 'term'),
    ('What was the reported average dividend in the Thank Use payout?', 'thank_use_patronage', '$55'),
    ('Who can explain Payment Protection benefits and limitations?', 'payment_protection', 'voluntary'),
    ('What is a certificate ladder and how does its $10,000 example work with early-withdrawal penalties?',
     'certificate_ladder', '$10,000'),
]


@pytest.mark.parametrize('question,pid,part', CASES)
def test_supported_policy_predicate_keeps_complete_evidence(ks_full, question, pid, part):
    query = parse(question, DAY, R)
    assert query.product_id == pid and query.attribute == 'description' and query.explicit_attribute
    answer = ks_full.answer(question, DAY)
    assert answer.confident and part.lower() in answer.text.lower()
    assert not answer.text.startswith(('Yes.', 'No.'))
    assert ks_full.explain(question, DAY)['answer'] == answer.text
    assert ks_full.answer(question, DAY) == answer


@pytest.mark.parametrize('question', [
    'What is the 30-year term for life insurance?',
    'What is the current APR on life insurance?',
    'What is the average dividend rate or APY for Thank Use?',
    'What is the maximum Payment Protection benefit amount?',
    'What is the early-withdrawal penalty rate for a certificate ladder?',
    'What term does Share Savings offer?',
    'What are the penalties on the regular certificate?',
])
def test_explicit_scalar_request_remains_unsupported(ks_full, question):
    assert parse(question, DAY, R).attribute != 'description'
    assert not ks_full.answer(question, DAY).confident


@pytest.mark.parametrize('question', [
    'Who was elected in the 78th board election and how long were their terms?',
    'What was the reported average dividend in the 2022 Thank Use payout?',
    'Who can explain the $500 Payment Protection benefits and limitations?',
    'What is a certificate ladder and how does its $20,000 example work with early-withdrawal penalties?',
])
def test_prose_disambiguation_preserves_unmatched_numeric_scope(ks_full, question):
    query = parse(question, DAY, R)
    assert query.question_numbers and query.attribute == 'description'
    assert not ks_full.answer(question, DAY).confident


@pytest.mark.parametrize('provider', ['Zephyrix', 'zephyrix', 'another bank'])
def test_other_provider_cannot_borrow_supported_information(ks_full, provider):
    question = 'How does {} life insurance compare term insurance and whole life?'.format(provider)
    assert not ks_full.answer(question, DAY).confident


def test_example_amount_is_retained_on_original_query():
    query = parse(CASES[-1][0], DAY, R)
    assert dict(query.slots)['amount'] == 10000 and ('$', 10000) in query.question_numbers


@pytest.mark.parametrize('question', [
    'Who can explain Zephyrix mobile wallet features?',
    'Who can explain another bank shared branching benefits?',
    'Who can explain $500 mobile wallet benefits?',
])
def test_legacy_catalog_does_not_bypass_reinterpreted_scope(ks_full, question):
    assert parse(question, DAY, R).prose_reinterpreted
    assert not ks_full.answer(question, DAY).confident


def test_serving_date_is_not_an_example_or_publication_claim(ks_full):
    base = 'How does life insurance compare term insurance and whole life'
    question = base + ' as of September 28, 2026?'
    query = parse(question, None, R)
    assert query.as_of == DAY and ('', 2026) in query.question_numbers and ('', 28) in query.question_numbers
    assert ks_full.answer(question).confident
    assert ks_full.answer('Explain mobile wallet.', DAY).confident


@pytest.mark.parametrize('has_percentage', [False, True])
def test_source_fraction_request_cannot_borrow_qualitative_background(has_percentage):
    from dataclasses import replace
    from conftest import make_fact
    from kb.claim_semantics import ClaimSemantics
    from kb.compose import render
    from kb.normalize import number_tokens
    from kb.question import Query
    from kb.resolve import resolve
    from kb.store import FactStore

    statement = '80% of participants completed the course.' if has_percentage else 'Participants received support.'
    unit = 'percent' if has_percentage else 'text'
    row = make_fact('membership', 'description', statement, unit=unit, value=80 if has_percentage else None,
                    extractor='curated', published='2026-03-01')
    semantic = ClaimSemantics(1, 'example.fraction', '0'*64, 'organization_fact' if has_percentage else 'description',
                              'eq' if has_percentage else 'none', 'participants' if has_percentage else '', '',
                              'single', (statement,), unit, '')
    row = replace(row, source=replace(row.source, quote=statement), semantics=semantic)
    store = FactStore(); store.add(row.source.snapshot_id, DAY, [row]); store.finalize()
    text = 'According to the March 2026 article, what percentage of participants completed the course?'
    q = Query('value', 'membership', 'description', (), DAY, False, text, number_tokens(text), 'synthetic')
    answer = render(resolve(q, store, R))
    assert answer.confident is has_percentage
    if has_percentage:
        assert statement in answer.text
    else:
        assert not answer.sources
