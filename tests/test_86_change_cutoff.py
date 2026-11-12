"""Serving cutoffs bound observed comparison evidence, separately from inline endpoints."""
from dataclasses import replace

import pytest

from conftest import make_fact
from kb.compose import render
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.store import FactStore

R = Registry.load()
DAYS = ('2026-05-12', '2026-08-27', '2026-09-28')


def store():
    result = FactStore()
    for i, day in enumerate(DAYS, 1):
        sid = '{}_{}'.format(i, day)
        f = make_fact('share_savings', 'apy', '{}%'.format(i), value=i, snapshot_id=sid)
        result.add(sid, day, [replace(f, source=replace(f.source, quote=f.value_text))])
    result.finalize()
    return result


def test_change_cannot_read_captures_after_explicit_serving_cutoff():
    q = parse('How did Share Savings APY change?', DAYS[1], R)
    assert q.as_of == q.serving_as_of == DAYS[1]
    plan = resolve(q, store(), R)
    answer = render(plan)
    assert plan.confident and answer.confident
    assert {f.source.snapshot_id for f in plan.facts} == {'1_'+DAYS[0], '2_'+DAYS[1]}
    assert '3%' not in answer.text and 'September' not in answer.text


@pytest.mark.parametrize('text,cutoff', [
    ('How did Share Savings APY change?', DAYS[0]),
    ('How did Share Savings APY change between August 27, 2026 and August 31, 2026?', DAYS[1]),
    ('How did Share Savings APY change between August 27, 2026 and August 31, 2026?', DAYS[2]),
    ('How did Share Savings APY change between May 12, 2026 and October 1, 2026?', None),
])
def test_unavailable_endpoint_and_single_capture_never_claim_unchanged(text, cutoff):
    answer = render(resolve(parse(text, cutoff, R), store(), R))
    assert not answer.confident and 'unchanged' not in answer.text and not answer.sources


def test_inline_range_remains_distinct_from_serving_argument():
    q = parse('How did Share Savings APY change between May 12, 2026 and August 27, 2026?', DAYS[1], R)
    answer = render(resolve(q, store(), R))
    assert answer.confident and '1%' in answer.text and '2%' in answer.text and '3%' not in answer.text


def test_unbounded_since_query_retains_historical_to_latest_behavior():
    q = parse('How did Share Savings APY change since May 2026?', None, R)
    assert q.serving_as_of is None
    answer = render(resolve(q, store(), R))
    assert answer.confident and '1%' in answer.text and '3%' in answer.text


def test_inline_as_of_is_a_cutoff_not_a_comparison_start():
    q = parse('How did Share Savings APY change as of August 27, 2026?', None, R)
    assert q.serving_as_of == DAYS[1]
    answer = render(resolve(q, store(), R))
    assert answer.confident and '1%' in answer.text and '2%' in answer.text
    assert '3%' not in answer.text and 'September' not in answer.text


def test_inline_cutoff_cannot_be_replaced_by_later_requested_endpoint():
    text = 'As of August 27, 2026, how did Share Savings APY change between May 12, 2026 and August 31, 2026?'
    assert not render(resolve(parse(text, None, R), store(), R)).confident


@pytest.mark.parametrize('endpoint,cutoff,expected', [
    ('September 2026', None, True),
    ('2026-09', None, True),
    ('September 30, 2026', None, False),
    ('end of September 2026', None, False),
    ('October 2026', None, False),
    ('August 2026', DAYS[1], True),
    ('September 2026', DAYS[1], False),
    ('September 2026, specifically September 30, 2026', None, False),
    ('September 2026, specifically September 29, 2026', None, False),
    ('August 2026, specifically August 28, 2026', DAYS[1], False),
])
def test_month_endpoint_selects_an_observed_capture_without_claiming_month_end(endpoint, cutoff, expected):
    q = parse('How did Share Savings APY change between May 2026 and '+endpoint+'?', cutoff, R)
    plan = resolve(q, store(), R)
    result = render(plan)
    assert result.confident is expected
    if expected:
        assert '1%' in result.text and '30, 2026' not in result.text
        assert all(f.source.snapshot_id.split('_')[1] <= (cutoff or DAYS[-1]) for f in plan.facts)


def test_inline_cutoff_is_not_a_requested_precise_endpoint_inside_a_bare_month():
    q = parse('As of September 28, 2026, how did Share Savings APY change between May and September 2026?', None, R)
    result = render(resolve(q, store(), R))
    assert result.confident and '1%' in result.text and '3%' in result.text


@pytest.mark.parametrize('cutoff', [None, DAYS[-1]])
def test_two_as_of_phrases_are_comparison_endpoints_not_a_single_serving_cutoff(cutoff):
    q = parse('Compare Share Savings APY as of May 2026 and as of September 2026.', cutoff, R)
    result = render(resolve(q, store(), R))
    assert result.confident and '1%' in result.text and '3%' in result.text
    precise = parse('Compare Share Savings APY as of May 12, 2026 and as of September 29, 2026.', cutoff, R)
    assert not render(resolve(precise, store(), R)).confident
