# section A: store
import pytest
from kb.store import FactStore, AsOfError
from kb.types import ClaimType, Fact, Source, make_key

def _f(sid, url, auth, eff, value):
    key = make_key("auto_loan", "apr", {"model_year_min": 2023, "model_year_max": 2026, "term_months": 60})
    src = Source(url, url, "rate_sheet" if auth == 3 else "calculator", auth, sid, "2026-09-28T00:00:00Z", 0, 0, "row")
    return Fact(key, "auto_loan", "apr", key[2], value, f"{value}% APR", "pct", ClaimType.RATE, eff, None, None, src, "rules", 1.0)

def _store():
    s = FactStore()
    s.add("01_2026-05-12_baseline", "2026-05-12", [_f("01_2026-05-12_baseline", "https://www.dupaco.com/rates", 3, "2026-05-01", 5.19)])
    s.add("05_2026-09-28_latest", "2026-09-28", [_f("05_2026-09-28_latest", "https://www.dupaco.com/rates", 3, "2026-08-31", 5.39), _f("05_2026-09-28_latest", "https://www.dupaco.com/calculators/vehicle-affordability", 1, "2026-01-01", 5.34)])
    s.finalize(); return s

# section A, pins beyond the brief's four: tie-breaks, as_of boundaries, the finalize contract
def _make_fact(url="https://www.dupaco.com/rates", auth=3, eff="2026-01-01", pub=None, fetched="2026-09-28T00:00:00Z", value=1.0):
    key = make_key("auto_loan", "apr", {"term_months": 60})
    src = Source(url, url, "rate_sheet", auth, "s", fetched, 0, 0, "row")
    return Fact(key, "auto_loan", "apr", key[2], value, f"{value}% APR", "pct", ClaimType.RATE, eff, None, pub, src, "rules", 1.0)

def _ordered(*facts, as_of=None):
    s = FactStore(); s.add("s", "2026-09-28", facts); s.finalize()
    return [f.value for f in s.in_force("s", "auto_loan", "apr", as_of)]

def _either_way(a, b):
    first, second = _ordered(a, b), _ordered(b, a)
    assert first == second  # the winner must not depend on which fact was added first
    return first

def test_equal_authority_newer_effective_date_wins_undated_last():
    old, new = _make_fact(eff="2026-01-01", value=1), _make_fact(eff="2026-03-01", value=2)
    undated = _make_fact(eff=None, pub="2026-09-01", value=3)  # the newest published_date of the three, and still last
    assert _either_way(old, new) == [2, 1]
    assert _ordered(old, undated, new) == [2, 1, 3] and _ordered(undated, new, old) == [2, 1, 3]
    assert _either_way(_make_fact(auth=3, eff="2026-01-01", value=4), _make_fact(auth=1, eff="2026-12-01", value=5)) == [4, 5]  # authority comes first

def test_published_then_fetched_then_url_break_remaining_ties():
    url_a, url_b = "https://www.dupaco.com/a", "https://www.dupaco.com/b"
    early, late = "2026-09-01T00:00:00Z", "2026-09-28T00:00:00Z"
    assert _either_way(_make_fact(pub="2026-02-01", value=1), _make_fact(pub="2026-03-01", value=2)) == [2, 1]
    assert _either_way(_make_fact(pub=None, value=1), _make_fact(pub="2026-03-01", value=2)) == [2, 1]  # no published_date orders last
    assert _either_way(_make_fact(fetched=early, value=1), _make_fact(fetched=late, value=2)) == [2, 1]
    assert _either_way(_make_fact(url=url_b, value=1), _make_fact(url=url_a, value=2)) == [2, 1]  # canonical_url ascending
    # each key outranks the next: published_date over fetched_at, fetched_at over canonical_url
    assert _either_way(_make_fact(pub="2026-03-01", fetched=early, value=1), _make_fact(pub="2026-02-01", fetched=late, value=2)) == [1, 2]
    assert _either_way(_make_fact(fetched=late, url=url_b, value=1), _make_fact(fetched=early, url=url_a, value=2)) == [1, 2]

def test_full_timestamp_beats_its_same_day_bare_date():
    # a page without fetched_at falls back to the crawl's bare taken_on date, so one snapshot can mix both forms
    bare, stamped = _make_fact(fetched="2026-09-28", value=1), _make_fact(fetched="2026-09-28T03:25:42.386Z", value=2)
    assert _either_way(bare, stamped) == [2, 1]
    assert _either_way(_make_fact(fetched="2026-09-29", value=3), stamped) == [3, 2]  # a later bare date still wins

def test_effective_on_the_as_of_day_is_kept_and_undated_always_kept():
    on_day, next_day, undated = _make_fact(eff="2026-08-31", value=1), _make_fact(eff="2026-09-01", value=2), _make_fact(eff=None, value=3)
    assert _ordered(on_day, next_day, undated, as_of="2026-08-31") == [1, 3]  # inclusive; effective one day later is out
    assert _ordered(on_day, next_day, undated, as_of="2026-09-01") == [2, 1, 3]
    assert _ordered(undated, as_of="1999-01-01") == [3]  # no effective_date: kept for any as_of
    assert _ordered(on_day, next_day, undated) == [2, 1, 3]  # no as_of: nothing is excluded

def test_as_of_on_a_crawl_day_selects_that_crawl_and_before_the_first_is_flagged():
    s = _store()  # crawls on 2026-05-12 and 2026-09-28
    assert s.snapshot_for("2026-05-12") == ("01_2026-05-12_baseline", "") and s.snapshot_for("2026-09-28") == ("05_2026-09-28_latest", "")
    assert s.snapshot_for("2026-09-27") == ("01_2026-05-12_baseline", "")  # between crawls: the earlier one
    assert s.snapshot_for("2026-05-11") == ("01_2026-05-12_baseline", "earliest crawl")  # the day before the first crawl

def test_facts_added_after_finalize_appear_after_the_next_finalize():
    s = _store()
    s.add("05_2026-09-28_latest", "2026-09-28", [_f("05_2026-09-28_latest", "https://www.dupaco.com/rates", 3, "2026-09-15", 5.45)])
    s.finalize()
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)] == [5.45, 5.39, 5.34]
    assert [f.value for f in s.in_force("01_2026-05-12_baseline", "auto_loan", "apr", None)] == [5.19]  # the other snapshot is untouched

def test_snapshot_without_facts_is_served_as_empty():
    s = _store()
    s.add("06_2026-10-05_empty", "2026-10-05", []); s.finalize()
    assert s.snapshot_for(None) == ("06_2026-10-05_empty", "") and s.in_force("06_2026-10-05_empty", "auto_loan", "apr", None) == []
    with pytest.raises(KeyError): s.in_force("07_never_added", "auto_loan", "apr", None)  # an id that was never added is a different case

def test_in_force_before_finalize_raises_instead_of_building():
    s = _store()
    s.add("05_2026-09-28_latest", "2026-09-28", [_f("05_2026-09-28_latest", "https://www.dupaco.com/rates", 3, "2026-09-15", 5.45)])
    with pytest.raises(RuntimeError, match="store not finalised"): s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)
    s.finalize()
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)] == [5.45, 5.39, 5.34]

def test_add_is_atomic_when_the_fact_iterable_raises():
    s = _store()
    def crawl(sid):  # one good fact, then a failure midway
        yield _f(sid, "https://www.dupaco.com/rates", 3, "2026-09-20", 9.99)
        raise OSError("crawl read failed")
    for sid, taken_on in (("06_2026-10-05_new", "2026-10-05"), ("05_2026-09-28_latest", "2026-09-28")):  # a new snapshot, then a known one
        with pytest.raises(OSError): s.add(sid, taken_on, crawl(sid))
    assert s.snapshots() == [("01_2026-05-12_baseline", "2026-05-12"), ("05_2026-09-28_latest", "2026-09-28")]
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)] == [5.39, 5.34]  # still finalised: the failed add invalidated nothing
    s.finalize()  # rebuilds from the raw lists, so a half-added batch would show up here
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)] == [5.39, 5.34]

def test_snapshot_for_contract():
    s = _store()
    assert s.snapshot_for(None) == ("05_2026-09-28_latest", "") and s.snapshot_for("2026-05-31") == ("01_2026-05-12_baseline", "")
    assert s.snapshot_for("2027-01-01") == ("05_2026-09-28_latest", "") and s.snapshot_for("2020-01-01") == ("01_2026-05-12_baseline", "earliest crawl")
    with pytest.raises(AsOfError): s.snapshot_for("yesterday")

def test_rank_prefers_authority_then_effective_date():
    s = _store()
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None)] == [5.39, 5.34]

def test_future_effective_fact_excluded():
    s = _store()
    assert [f.value for f in s.in_force("05_2026-09-28_latest", "auto_loan", "apr", "2026-08-30")] == [5.34]

def test_finalize_is_idempotent():
    s = _store(); before = s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None); s.finalize()
    assert s.in_force("05_2026-09-28_latest", "auto_loan", "apr", None) == before

# tests/test_20_resolve.py  (section B)
from kb.resolve import resolve
from kb.question import parse
from kb.registry import Registry
R = Registry.load()
def _plan(store, question, as_of=None): return resolve(parse(question, as_of, R), store, R)
def _values(plan): return sorted(f.value for f in plan.facts)

def test_mortgage_without_amount_enumerates_tiers(store_full):
    p = _plan(store_full, "Can you tell me the interest rate for a 30-year mortgage?")
    assert {7.13, 7.25} <= set(_values(p)) and ("%", 6.061) not in p.permitted_values

def test_highest_share_savings_tier(store_full):
    p = _plan(store_full, "What is the highest Share Savings APY?")
    assert _values(p) == [0.20] and ("$", 25000.0) in p.permitted_values and ("%", 0.35) not in p.permitted_values

def test_amount_picks_narrowest_tier(store_full):
    assert _values(_plan(store_full, "If I keep $15,000 in Share Savings, what APY do I earn?")) == [0.15]

def test_model_year_and_term(store_full):
    assert _values(_plan(store_full, "What rate would I get on a 60-month loan for a 2026 car?")) == [5.39]

def test_as_of_uses_the_snapshot_in_force(store_full):
    p = _plan(store_full, "What was the rate on the 10-month fixed jumbo special certificate as of May 2026?", "2026-05-31")
    assert _values(p) == [3.90] and p.snapshot_id == "02_2026-05-19_recrawl"

def test_refusal_first_for_unpublished_attribute(store_full):
    for q in ("What is your rate on a 7/1 adjustable-rate mortgage?", "What interest rate do you charge on a construction loan?", "Can you give me the lobby hours for the Mullan Avenue branch?"):
        assert _plan(store_full, q).confident is False

def test_two_products_enumerated_in_fixed_order(store_full):
    p = _plan(store_full, "What are the APRs on the Platinum Visa and the Rewards Visa?")
    assert [f.product_id for f in p.facts][:2] == ["platinum_visa", "rewards_visa"]

# section B, pins beyond the brief's seven: the controller rulings and the canonicaliser addendum
from kb.normalize import number_tokens
from kb.question import Query
from kb.resolve import EARLIEST_NOTE, TIER_SELECTORS, select_tier

def _tier(value, **quals):
    key = make_key("p", "apy", quals)
    src = Source("u", "u", "rate_sheet", 3, "s", "2026-09-28", 0, 0, "row")
    return Fact(key, "p", "apy", key[2], value, f"{value}%", "pct", ClaimType.RATE, None, None, None, src, "rules", 1.0)

def _ask(**slots): return Query("value", "p", "apy", tuple(sorted(slots.items())), None, False, "", frozenset(), "")

def test_decision_table_on_synthetic_tiers():
    loans = [_tier(7.13, loan_amount_max=100000.0), _tier(7.25, loan_amount_max=200000.0)]  # "or less" tiers
    assert [f.value for f in select_tier(loans, _ask(amount=100000.0))] == [7.13]  # inclusive bound, narrowest tier
    assert [f.value for f in select_tier(loans, _ask(amount=150000.0))] == [7.25] and select_tier(loans, _ask(amount=250000.0)) == []
    cars = [_tier(5.39, model_year_min=2023, model_year_max=26), _tier(5.64, model_year_min=2020, model_year_max=22)]
    assert [f.value for f in select_tier(cars, _ask(model_year=2026))] == [5.39]  # "2023-26" ends in 2026
    hours = [_tier(1.0, day="monday"), _tier(2.0, day="tuesday")]
    assert [f.value for f in select_tier(hours, _ask(day="tuesday"))] == [2.0]
    assert [f.value for f in select_tier(hours, _ask(day="sunday"))] == [1.0, 2.0]  # a day narrows, never refuses
    assert [f.value for f in select_tier(hours + loans, _ask(superlative="lowest"))] == [1.0]

def test_certificate_term_resolves_from_the_sibling_product(store_full):
    for question in ("How much does the 17-month CD pay?", "Do you have a 17-month CD?"):  # cert_regular has no 17-month row
        assert [(f.product_id, f.value) for f in _plan(store_full, question).facts] == [("cert_special", 4.10)]
    assert _plan(store_full, "What is the APY on the 25-month certificate special right now?").confident is False  # a dropped term

def test_term_question_skips_the_jumbo_row_unless_asked(store_full):
    assert _values(_plan(store_full, "What is the APY on Dupaco's 17-month special certificate?")) == [4.10]
    assert _values(_plan(store_full, "What is the APY on the 10-month jumbo certificate special?")) == [4.00]

def test_list_enumerates_the_family_personal_first(store_full):
    cards = ["platinum_visa", "rewards_visa", "business_platinum_visa", "business_rewards_visa"]
    assert R.family("rewards_visa") == "credit_card" and R.products_in_family("credit_card") == cards
    p = _plan(store_full, "What credit cards do you offer and what are their APRs?")  # business cards kept, intro rows dropped
    assert [f.product_id for f in p.facts] == cards and not any(dict(f.qualifiers).get("intro") for f in p.facts)
    assert [f.product_id for f in _plan(store_full, "What are the APRs on your business credit cards?").facts] == cards[2:]
    assert [f.product_id for f in _plan(store_full, "What personal credit cards do you offer and their APRs?").facts] == cards[:2]

def test_pre_crawl_date_answers_from_the_earliest_crawl(store_full):
    p = _plan(store_full, "What is the APY on the 10-month certificate special?", "2026-01-15")
    assert p.snapshot_id == "01_2026-05-12_baseline" and _values(p) == [3.80]  # dated facts kept
    assert p.conflict_note == EARLIEST_NOTE and not number_tokens(p.conflict_note)

def test_malformed_date_unknown_product_and_spans_refuse_cleanly(store_full):
    for question, as_of in (("What is the APY on Share Savings?", "not-a-date"), ("What is the APY on the Jump Start savings account?", None), ("What is your rate on a 7/1 adjustable-rate mortgage?", None)):
        p = _plan(store_full, question, as_of)
        assert p.confident is False and not p.facts and number_tokens(p.refusal_span) <= number_tokens(question)
    assert _plan(store_full, "What is your rate on a 7/1 adjustable-rate mortgage?").refusal_span == "that"  # review round W1: no number

def test_branch_name_matches_words_of_the_address(store_full):
    p = _plan(store_full, "What is the address of the Galena Branch?")
    assert [f.value_text for f in p.facts] == ["11375 Oldenburg Ln., Galena, IL, 61036"] and ("", 61036.0) in p.permitted_values

def test_stale_and_lower_authority_tiers_never_win(store_full):
    assert sorted(TIER_SELECTORS) == ["balance", "loan_amount", "model_year", "segment", "term"]
    assert _values(_plan(store_full, "What's the APR for a 60-month auto loan on a 2025 model-year vehicle?")) == [5.39]  # not the calculator's 5.34
    assert _values(_plan(store_full, "What is the APR on a 36-month ATV loan for a 2019 model year?", "2026-05-12")) == [8.89]  # no stale 2018-19 row
    p = _plan(store_full, "Provide current checking account interest rates")
    assert p.facts and all(f.confidence == 1.0 for f in p.facts) and 3.0 not in _values(p)

def _row(value, auth, eff, confidence=1.0, **quals):
    key = make_key("auto_loan", "apr", quals)
    url = "https://www.dupaco.com/" + ("rates" if auth == 3 else "calculators/vehicle-affordability")
    src = Source(url, url, "rate_sheet" if auth == 3 else "calculator", auth, "s", "2026-09-28", 0, 0, "row")
    return Fact(key, "auto_loan", "apr", key[2], value, f"{value}% APR", "pct", ClaimType.RATE, eff, None, None, src, "rules", confidence)

def test_only_top_authority_table_rows_become_tiers():
    s = FactStore()
    s.add("s", "2026-09-28", [_row(5.39, 3, "2026-08-31", term_months=60), _row(5.44, 1, "2026-09-15", term_months=72), _row(5.99, 3, "2026-08-31", confidence=0.5)])
    s.finalize()
    assert _values(_plan(s, "What is the APR on an auto loan?")) == [5.39]  # no inline sentence, no calculator-only tier
    assert _plan(s, "What is the APR for a 72-month auto loan?").confident is False  # a term only the calculator lists

def test_change_plan_holds_the_from_crawl_then_the_latest(store_full):
    p = _plan(store_full, "Has the 36-month personal loan APR changed since May 2026?")
    assert [(f.source.snapshot_id, f.value) for f in p.facts] == [("02_2026-05-19_recrawl", 10.49), ("05_2026-09-28_latest", 10.49)]

def test_rate_rows_carry_their_apr_companion(store_full):
    p = _plan(store_full, "What is the 20-year mortgage rate?")
    assert [(f.attribute, f.value) for f in p.facts] == [("rate", 7.13), ("apr", 7.26)]

# section B, fix round 1 pins
from kb.types import AnswerPlan

def _query(product_id, attribute, **slots):
    return Query("value", product_id, attribute, tuple(sorted(dict(segment="personal", **slots).items())), None, False, "", frozenset(), "")

def test_special_question_never_answers_with_a_regular_rate(store_full):
    for question in ("What is the APY on the 24-month certificate special?", "Was a 12-month certificate special offered in mid-May 2026?", "What is the APY on the 18-month IRA certificate special?"):
        assert _plan(store_full, question).confident is False, question

# Gate fix item 2: the IRA phrasings resolve to the IRA rows (pinned by product and label: Roth's 4.00% equals the
# personal special's).
def test_ira_phrasings_resolve_to_the_ira_rows(store_full):
    from kb.compose import render
    for question, program, value in (("What is the APY on the Traditional IRA 10 month fixed jumbo special certificate?", "traditional", 3.90),
                                     ("What is the APY on the Roth IRA 10 month fixed jumbo special certificate?", "roth", 4.00)):
        p = _plan(store_full, question)
        assert [(f.product_id, dict(f.qualifiers)["program"], f.value) for f in p.facts] == [("ira_cert", program, value)], question
        assert render(p).text == "{} 10 Month Fixed Jumbo Special IRA Certificate: {:.2f}% APY.".format(program.title(), value)
    p = _plan(store_full, "What is the APY on IRA savings?")
    assert p.confident and {f.product_id for f in p.facts} == {"ira_variable"} and len(p.facts) == 6  # Roth and Traditional tiers
    p = _plan(store_full, "What is the APY on the 10 month fixed jumbo special certificate?")
    assert [(f.product_id, f.value) for f in p.facts] == [("cert_special", 4.00)]

def test_both_named_segments_list_every_card(store_full):
    ids = [f.product_id for f in _plan(store_full, "What are the APRs on your personal and business credit cards?").facts]
    assert ids == ["platinum_visa", "rewards_visa", "business_platinum_visa", "business_rewards_visa"]

def test_sources_cite_every_in_force_page_with_the_value(store_full):
    p = _plan(store_full, "As of June 15, 2026, what was the rate on a 15-year fixed conventional mortgage?")  # dev-004
    assert "https://www.dupaco.com/personal/loans/home-loans" in {s.canonical_url for s in p.sources}

def test_plan_carries_its_date_and_the_date_numbers(store_full):
    p = _plan(store_full, "What was the rate on the 10-month fixed jumbo special certificate as of May 2026?", "2026-05-31")
    assert p.as_of == "2026-05-31" and ("", 2026.0) in p.permitted_values
    assert _plan(store_full, "What is the highest Share Savings APY?").as_of is None
    early = _plan(store_full, "What is the APY on the 10-month certificate special?", "2026-01-15")
    assert early.as_of == "2026-01-15" and early.conflict_note == EARLIEST_NOTE and ("", 2026.0) in early.permitted_values
    change = _plan(store_full, "Has the 36-month personal loan APR changed since May 2026?")  # crawls of May 19 and September 28
    assert change.as_of == "2026-05-31" and {("", 19.0), ("", 28.0), ("", 2026.0)} <= change.permitted_values
    assert AnswerPlan("value", (), frozenset(), (), True, None, None).as_of is None  # positional construction still works

def test_minimum_attributes_fall_back_to_the_published_one(store_full):
    p = resolve(_query("cert_special", "min_to_open", special=True, term_months=17), store_full, R)  # certificates publish only min_to_earn
    assert [(f.attribute, f.value) for f in p.facts] == [("min_to_earn", 1000.0)]
    assert {f.attribute for f in resolve(_query("share_savings", "min_to_open"), store_full, R).facts} == {"min_to_open"}
    assert {f.attribute for f in resolve(_query("share_savings", "min_to_earn"), store_full, R).facts} == {"min_to_earn"}

# section B, pre-gate wave A pins
import dataclasses
from itertools import groupby
from kb import tiers
from kb.compose import render

def test_display_name_numbers_are_permitted(store_full):
    p = _plan(store_full, "Provide current checking account interest rates")  # dup-052: every row label reads "1st Rate Checking"
    assert {"first_rate_checking", "business_checking"} <= {f.product_id for f in p.facts}
    assert {t for t in p.permitted_values if t[0] == ""} == {("", 1.0)}  # its tier bounds are all money
    assert number_tokens(render(p).text) <= p.permitted_values  # a non-refusal answer holds only permitted numbers
    assert _plan(store_full, "What is the highest Share Savings APY?").permitted_values == {("%", 0.20), ("$", 25000.0)}  # no digit in the name

def test_list_specials_order_the_rows_rather_than_filter_them(store_full):
    plain = sorted(map(repr, _plan(store_full, "What CD rates do you have?").facts))
    for question in ("What CD rates do you have, including specials?", "What are all your certificate rates, including the specials?",
                     "List all certificate terms and APYs, specials included."):
        facts = _plan(store_full, question).facts
        assert sorted(map(repr, facts)) == plain, question  # every row of the family, the regular ones included
        assert {"cert_regular", "business_cert_regular"} <= {f.product_id for f in facts} and dict(facts[0].qualifiers)["special"] is True
        for pid in dict.fromkeys(f.product_id for f in facts):  # the special rows first within each product
            flags = [bool(dict(f.qualifiers).get("special")) for f in facts if f.product_id == pid]
            assert flags == sorted(flags, reverse=True), (question, pid)
    assert _plan(store_full, "What is the APY on the 18-month IRA certificate special?").confident is False  # a value keeps the hard filter

def test_selector_is_still_importable_from_resolve():
    from kb.resolve import Selector
    assert Selector is tiers.Selector

def _named(q, *ids): return dataclasses.replace(q, product_ids=ids)
def _runs(plan): return [pid for pid, _ in groupby(f.product_id for f in plan.facts)]  # one entry per run of a product

def test_named_products_list_only_themselves_in_question_order(store_full):
    loans = parse("What are the rates on auto loans and personal loans?", None, R)
    assert _runs(resolve(_named(loans, "auto_loan", "personal_loan"), store_full, R)) == [
        "auto_loan", "personal_loan"]  # A18: named products stay scoped
    cards = ["platinum_visa", "rewards_visa"]
    mixed = parse("What are the APRs on the Platinum Visa and the auto loan?", None, R)
    assert _runs(resolve(_named(mixed, "platinum_visa", "auto_loan"), store_full, R)) == ["platinum_visa", "auto_loan"]
    same = parse("What are the APRs on the Platinum Visa and the Rewards Visa?", None, R)
    for ids in (("platinum_visa", "rewards_visa"), ("rewards_visa", "platinum_visa")):  # one family: the plan does not change
        assert resolve(_named(same, *ids), store_full, R).facts == resolve(same, store_full, R).facts and _runs(resolve(same, store_full, R)) == cards
    value = _named(_query("share_savings", "apy"), "share_savings", "first_rate_checking")  # a value question expands no family
    assert _runs(resolve(value, store_full, R)) == ["share_savings", "first_rate_checking"]

# section B, pre-gate wave A fix round 1 pins: the canonicaliser's own product_ids
from scoring import REFUSAL_RE

def test_mixed_segment_lists_keep_every_named_product(store_full):
    # a named product's family stays in the question's segment only when the product is of that segment
    cases = (("What are the APYs on business savings and IRA certificates?", ("business_savings", "ira_cert"),
              ["business_savings", "ira_cert"]),
             ("What are the APRs on the business Platinum Visa and the auto loan?", ("business_platinum_visa", "auto_loan"),
              ["business_platinum_visa", "auto_loan"]),
             ("What are the APYs on business money market accounts and Share Savings?", ("business_money_market", "share_savings"), ["business_money_market", "share_savings"]),
             ("What are the APRs on the Platinum Visa and the Business Platinum Visa?", ("platinum_visa", "business_platinum_visa"),
              ["platinum_visa", "business_platinum_visa"]))
    for question, named, runs in cases:
        q = parse(question, None, R)
        assert q.product_ids == named and dict(q.slots)["segment"] == "business", question  # the whole question reads business
        p = resolve(q, store_full, R)
        assert p.confident and set(named) <= {f.product_id for f in p.facts}, question  # no named product dropped or swapped
        assert runs is None or _runs(p) == runs, question
    money = {f.product_id for f in _plan(store_full, cases[2][0]).facts}
    assert money == {"business_money_market", "share_savings"}  # A18: both aliases name products

def test_named_products_start_with_product_id(store_full):
    value = _query("share_savings", "apy")
    assert _runs(resolve(_named(value, "first_rate_checking", "share_savings"), store_full, R)) == ["share_savings", "first_rate_checking"]
    assert _runs(resolve(value, store_full, R)) == ["share_savings"]  # a hand-built Query: product_ids is ()

def _shows(text, plan, pid):
    """A rendered line names ``pid`` and shows one of its APRs."""
    values = [f.value_text for f in plan.facts if f.product_id == pid and f.attribute == "apr"]
    return any(R.display_name(pid) in line and any(v in line for v in values) for line in text.splitlines())

def test_cross_family_lists_render_every_named_product(store_full):
    for question, named in (("What are the rates on auto loans and personal loans?", ("auto_loan", "personal_loan")),
                            ("What are the APRs on the Platinum Visa and the auto loan?", ("platinum_visa", "auto_loan")),
                            ("APRs on the business Platinum Visa and the auto loan", ("business_platinum_visa", "auto_loan"))):
        p = _plan(store_full, question)
        a = render(p)
        assert a.confident and not REFUSAL_RE.search(a.text), question
        assert all(_shows(a.text, p, pid) for pid in named), (question, a.text)
        assert number_tokens(a.text) <= p.permitted_values, question  # every number the answer prints is permitted

def test_plans_carry_the_question_span(store_full):
    for question in ("  What is the highest Share Savings APY?  ", "What is the APY on the 25-month certificate special right now?"):  # an answer, a refusal
        p = _plan(store_full, question)
        assert p.question == parse(question, None, R).raw_span == question.strip(), question  # the cut span, digits kept
    assert AnswerPlan("value", (), frozenset(), (), True, None, None).question is None  # positional construction still works

def test_routing_number_cites_every_page_that_states_it(store_full):
    p = _plan(store_full, "What is Dupaco's routing number?")  # dup-054 expects /business/cash-management
    assert [f.value_text for f in p.facts] == ["273974581"]
    assert {"https://www.dupaco.com/business/cash-management", "https://www.dupaco.com/contact"} <= {s.canonical_url for s in p.sources}
