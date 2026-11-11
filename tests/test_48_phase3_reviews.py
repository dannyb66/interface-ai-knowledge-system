"""Independent review regressions: mixed dated pools, visibility, ranking and parser carries."""
from itertools import permutations
from conftest import make_fact
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.store import FactStore
from kb.temporal import key_history, select_dated

R = Registry.load()
SID = "01_2026-05-12_baseline"


def count(text, date, authority=1, url="https://www.dupaco.com/old", **qualifiers):
    return make_fact("branch_count", "count", text, snapshot_id=SID, published=date,
                     authority=authority, url=url, extractor="prose", **qualifiers)


def store(facts):
    out = FactStore()
    out.add(SID, "2026-05-12", facts)
    out.finalize()
    return out


def test_mixed_pool_cannot_disable_publication_cut_or_add_future_citation():
    old = count("23 branches", "2025-01-01")
    future = count("23 branches", "2026-05-11", 4, "https://www.dupaco.com/future")
    undated = count("999 branches", None, 9, "https://www.dupaco.com/undated")
    q = parse("How many branches?", "2025-12-31", R)
    for ordering in permutations([old, future, undated]):
        plan = resolve(q, store(ordering), R)
        assert plan.confident and plan.facts == (old,)
        assert [s.canonical_url for s in plan.sources] == [old.source.canonical_url]


def test_unrelated_undated_keys_stay_visible(ks_full):
    from dataclasses import replace
    old = count("23 branches", "2025-01-01")
    plain = count("999 branches", None, 9, item="separate")
    q = parse("How many branches?", "2025-12-31", R)
    assert set(resolve(q, store([old, plain]), R).facts) == {old, plain}
    answer = ks_full.answer("What is the Galena branch address?", "2026-06-01")
    assert answer.confident and "11375 Oldenburg" in answer.text


def test_publication_order_and_missing_history_are_observable():
    old = count("23 branches", "2024-01-01", 9)
    new = count("22 branches", "2025-01-01", 0, "https://www.dupaco.com/new")
    for ordering in permutations([old, new]):
        data = store(ordering)
        data.add("02_2026-05-19_recrawl", "2026-05-19", [])
        data.finalize()
        assert select_dated(ordering, None) == [new]
        assert key_history(data, new.key) == [(SID, new), ("02_2026-05-19_recrawl", None)]


def test_count_relative_year_is_not_a_rate_year_back(ks_full):
    for word in ("last", "previous", "prior"):
        q = "How many employees used Volunteer Time Off in the {} year?".format(word)
        parsed = parse(q, None, R)
        assert "year_back" not in dict(parsed.slots) and not parsed.past
        answer = ks_full.answer(q)
        assert answer.confident and "256" in answer.text and "294" in answer.text


def test_count_year_never_comes_from_a_question_date(ks_full):
    base = "How many employees used Volunteer Time Off"
    for phrase in ("as of 2025-05-01", "as of 2025-05", "as of May of 2025"):
        q = parse(base + " " + phrase + "?", None, R)
        assert "year" not in dict(q.slots), phrase
        answer = ks_full.answer(base + " " + phrase + "?")
        assert answer.confident and "256" in answer.text and "294" in answer.text
    assert dict(parse(base + " in 2024?", None, R).slots)["year"] == 2024


def test_partner_prose_never_becomes_dupaco_boilerplate_counts():
    from kb.article_facts import counts
    from kb.extract_rules import SourceContext
    ctx = SourceContext("https://www.dupaco.com/newsroom/a", "https://www.dupaco.com/newsroom/a",
                        "newsroom", 1, SID, "2026-05-12")
    line = "A partner bank reports that it has 12 employees and 2 branch office locations."
    assert counts([line], [], (0, 0), ctx, "2026-05-01") == []


def test_branch_aliases_and_unlisted_contact_modes(ks_full):
    assert "(608) 282-6000" in ks_full.answer("Phone number of the E. Washington branch?").text
    assert "2245 Flint Hill" in ks_full.answer("What is the Key West branch address?").text
    assert "8:30 a.m." in ks_full.answer("What are the Edgewood Road lobby hours?").text
    for question in ("Highway 20 branch lobby hours?", "E. Business Hwy. 151 branch hours?",
                     "What is the Platteville lobby fax number?", "What is the Platteville lobby email?",
                     "Is the branch closed today?"):
        assert not ks_full.answer(question).confident, question
    assert "closed" in ks_full.answer("Is the Hy-Vee branch still operating?").text
    assert parse("Is there a branch close to Hy-Vee?", None, R).intent != "status"


def test_typo_only_when_unique_and_terms_cover_full_number_word_range():
    from kb.qslots import fix_typo
    from kb.normalize import number_word, question_term
    assert fix_typo("batle", {"battle": "battle", "bottle": "bottle"}) == "battle"
    assert fix_typo("catle", {"cable": "cable", "cattle": "cattle"}) == "catle"
    assert number_word("ninety-nine") == 99 and question_term("ninety-nine month CD") == (99, False, False)


def test_mentions_preserve_unpriced_programs_and_change_endpoints(ks_full):
    refused = ks_full.answer("What are the APRs on the 30-year FHA mortgage and the 15-year FHA mortgage?")
    assert not refused.confident and "%" not in refused.text
    mixed = ks_full.answer("Compare the 60-month auto loan APR with the 30-year FHA mortgage APR.")
    assert not mixed.confident and "%" not in mixed.text
    changed = ks_full.answer("How did the 10-month and 17-month certificate special APYs change between June and August 2026?")
    assert changed.confident and "3.85%" in changed.text and "3.95%" in changed.text
    plan = resolve(ks_full._parse("How did the 10-month and 17-month certificate special APYs change between June and August 2026?", None), ks_full.store, R)
    assert {f.source.snapshot_id for f in plan.facts} == {"03_2026-06-09_recrawl", "04_2026-08-27_rebaseline"}
    words = parse("Compare twenty-one-year and thirty-year mortgage rates.", None, R)
    assert [dict(m)["term_months"] for m in words.mentions] == [252, 360]


def test_one_sided_change_never_claims_an_unchanged_value(ks_full):
    new = ks_full.answer("How did the 17-month certificate special APY change between May 12 and June 9, 2026?")
    old = ks_full.answer("How did the 25-month certificate special APY change between May 12 and September 28, 2026?")
    assert "3.85%" in new.text and "it is" in new.text and "unchanged" not in new.text
    assert "3.60%" in old.text and "it was" in old.text and "unchanged" not in old.text


def test_change_point_requires_a_current_key_and_dates_first_supported_crawl(ks_full):
    assert not ks_full.answer("When did the 25-month certificate special APY change?").confident
    data = FactStore()
    data.add(SID, "2026-05-12", [])
    for sid, day in (("02_2026-05-19_recrawl", "2026-05-19"), ("03_2026-05-26_recrawl", "2026-05-26")):
        data.add(sid, day, [make_fact("share_savings", "apy", "1.20%", value=1.2, snapshot_id=sid)])
    data.finalize()
    plan = resolve(parse("When did the Share Savings APY change?", None, R), data, R)
    assert plan.confident and [f.source.snapshot_id for f in plan.facts] == ["02_2026-05-19_recrawl", "03_2026-05-26_recrawl"]


def test_latest_model_year_selects_the_newest_available_band_per_crawl(ks_full):
    for wording, date, bounds, rate in (("newest", "2026-08-27", (2023, 2026), "5.19%"),
                                      ("latest", None, (2024, 2027), "5.39%")):
        text = "What is the 60-month auto loan APR for the {} model-year tier?".format(wording)
        q = parse(text, date, R)
        assert dict(q.slots)["latest_model_year"] is True
        plan = resolve(q, ks_full.store, R)
        assert plan.confident and len(plan.facts) == 1
        qualifiers = dict(plan.facts[0].qualifiers)
        assert (qualifiers["model_year_min"], qualifiers["model_year_max"]) == bounds
        assert qualifiers["term_months"] == 60 and rate in ks_full.answer(text, date).text


def test_whole_auto_table_keeps_supported_older_model_year_labels(ks_full):
    text = "Did the auto loan rate table change between August and September 2026?"
    q = parse(text, None, R)
    assert "latest_model_year" not in dict(q.slots)
    plan = resolve(q, ks_full.store, R)
    assert plan.confident and len({dict(f.qualifiers)["model_year_min"] for f in plan.facts}) > 2
    answer = ks_full.answer(text).text
    assert all(value in answer for value in ("5.19%", "5.39%", "2020", "2021"))


def test_latest_model_year_is_explicit_and_independent_of_row_order():
    from kb.tiers import select_tier
    text = "What is the APR for the newest model-year tier on a 60-month auto loan?"
    q = parse(text, None, R)
    old = make_fact("auto", "apr", "7.00%", value=7, term_months=60, model_year_min=2019, model_year_max=2022)
    new = make_fact("auto", "apr", "6.00%", value=6, term_months=60, model_year_min=2023, model_year_max=2026)
    other_term = make_fact("auto", "apr", "5.00%", value=5, term_months=72, model_year_min=2024, model_year_max=2027)
    for ordering in permutations([old, new, other_term]):
        assert select_tier(ordering, q) == [new]
    assert "latest_model_year" not in dict(parse("What is the latest auto loan APR?", None, R).slots)
