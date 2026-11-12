"""Ranking positions never borrow recognition counts or another event's scope."""
from dataclasses import replace

import pytest

from conftest import make_fact
from kb.claim_semantics import ClaimSemantics
from kb.compose import render
from kb.normalize import number_tokens
from kb.question import Query
from kb.recognition_scope import recognition_scope_supported
from kb.registry import Registry
from kb.resolve import resolve
from kb.store import FactStore

R = Registry.load()
DAY = '2026-09-28'


def query(text, intent='value'):
    return Query(intent, 'forbes_recognition', 'description', (), DAY, False, text, number_tokens(text), 'synthetic')


def fact(text, *, published='2024-03-01', event=None, typed=False):
    row = make_fact('forbes_recognition', 'description', text, published=published, event=event,
                    unit='count' if typed else 'text', value=7 if typed else None, extractor='curated',
                    url='https://example.test/news/atlas-top-credit-union')
    semantic = ClaimSemantics(1, 'example.rank', '0'*64, 'organization_fact', 'eq', 'overall rank', '',
                              'single', (text,), 'count', '') if typed else None
    return replace(row, source=replace(row.source, quote=text), semantics=semantic)


@pytest.mark.parametrize('text', [
    'Where did Example place in Atlas small-employer rankings?',
    'What position did Example rank in the Atlas survey?',
    'How high did Example rank in Atlas rankings?',
    'Did Example rank seventh in the Atlas survey?',
])
def test_occurrence_ordinal_does_not_supply_ranking_position(text):
    row = fact('This was the seventh time Atlas recognized Example.')
    assert not recognition_scope_supported(query(text), [row], R)


@pytest.mark.parametrize('text', [
    'How many times has Atlas recognized Example as a small employer?',
    'How many times has Zephyrix recognized Example as a top credit union?',
    'How many times has Atlas ranked Example in 2023?',
    'How many times has Atlas recognized Example in 2026?',
    'How many times has Atlas ranked Example at #61?',
    'How many times has Atlas ranked Example first?',
    'How often has Atlas ranked Example seventh?',
    'How many times has Atlas ranked Example 7th?',
])
def test_category_provider_year_and_specific_rank_remain_hard_scope(text):
    row = fact('This was the seventh time Atlas recognized Example.')
    assert not recognition_scope_supported(query(text, 'count'), [row], R)


@pytest.mark.parametrize('text', [
    'How many times has Atlas recognized Example?',
    'How many times has Atlas ranked Example among the top credit unions?',
    'How many times has Atlas recognized Example in 2024?',
    'How many times has Atlas ranked Example in 2024?',
    'How many times has Atlas recognized Example as of September 28, 2026?',
])
def test_supported_frequency_counts_keep_verified_source_scope(text):
    row = fact('This was the seventh time Atlas recognized Example.')
    assert recognition_scope_supported(query(text, 'count'), [row], R)


def test_preserved_typed_position_survives_and_published_year_is_not_an_event_substitute():
    text = 'Forbes ranked Dupaco #7 overall among small employers in 2023.'
    row = fact(text, typed=True)
    q = query('Where did Dupaco place in Forbes 2023 small-employer rankings?')
    assert recognition_scope_supported(q, [row], R)
    assert not recognition_scope_supported(query('Where did Dupaco place in Forbes 2022 small-employer rankings?'), [row], R)
    assert not recognition_scope_supported(query('Where did Dupaco place in Forbes 2024 small-employer rankings?'), [row], R)
    assert recognition_scope_supported(query('According to the 2024 article, where did Dupaco place in Forbes 2023 small-employer rankings?'), [row], R)
    assert not recognition_scope_supported(q, [replace(row, semantics=None)], R)
    store = FactStore(); store.add(row.source.snapshot_id, DAY, [row]); store.finalize()
    answer = render(resolve(q, store, R))
    assert answer.confident and text in answer.text and answer.sources


def test_negated_position_is_not_a_complete_ranking_answer():
    row = fact('Forbes was not ranked #7 overall.', typed=True)
    assert not recognition_scope_supported(query('Where did Forbes rank?'), [row], R)


@pytest.mark.parametrize('question', [
    'Where did Dupaco place in Forbes 2023 small-employer rankings?',
    'What was Dupaco\'s position in Forbes small-employer rankings?',
    'How many times has Forbes recognized Dupaco as a small employer in 2023?',
    'How many times has Forbes ranked Dupaco as a small employer?',
    'Is the fifth Forbes recognition from 2023?',
    'What did Forbes say about Dupaco in 2023?',
])
def test_installed_unsupported_recognition_scope_refuses_with_cache_explain_parity(ks_full, question):
    answer = ks_full.answer(question, DAY)
    assert not answer.confident and not answer.sources and not answer.conflict_note
    assert number_tokens(answer.text) <= number_tokens(question)
    assert ks_full.answer(question, DAY) == answer
    explained = ks_full.explain(question, DAY)
    assert explained['answer'] == answer.text and not explained['confident']


@pytest.mark.parametrize('question', [
    'How many times has Forbes recognized Dupaco?',
    'How many times has Forbes named Dupaco a top credit union?',
    'How many times has Forbes ranked Dupaco among the best credit unions?',
    'Give the details of Dupaco\'s Forbes Recognition.',
    'What is known about Dupaco\'s Forbes Recognition?',
])
def test_installed_supported_counts_remain_confident(ks_full, question):
    answer = ks_full.answer(question, DAY)
    assert answer.confident and 'fifth time' in answer.text and answer.sources
