# tests/test_22_temporal.py
from pathlib import Path
from conftest import make_fact
from kb.temporal import published_date, select_dated, status_at, cutoff
from kb.types import ClaimType
S05 = Path("snapshots/05_2026-09-28_latest/pages")

def _page(prefix): return next(S05.glob(prefix + "*.md")).read_text(encoding="utf-8")
def _page_at(crawl, prefix): return next(Path("snapshots", crawl, "pages").glob(prefix + "*.md")).read_text(encoding="utf-8")
def _count(text, pub, authority=1, url="https://www.dupaco.com/newsroom/a", **kw):  # kw: snapshot_id, qualifiers (pins below)
    return make_fact("branch_count", "count", text, extractor="prose", claim=ClaimType.ASSERTION, unit="count",
                     published=pub, authority=authority, url=url, page_type="newsroom", **kw)

def test_published_date_reads_the_header_only():
    assert published_date(_page("newsroom-volunteering-pays-off-dupaco-credit-union-employees-reap-the-benefits-of-giving-b-bbbfc4")) == "2025-04-21"
    assert published_date(_page("newsroom-dupaco-community-credit-union-celebrates-completion-of-expanded-branch")) == "2021-07-23"
    assert published_date(_page("rates-59a9e6")) is None

def test_published_date_reads_bylines_and_front_matter():  # ruling 2026-11-06; gap research #5
    assert published_date(_page_at("03_2026-06-09_recrawl", "newsroom-dupaco-community-credit-union-celebrates-mineral-point-branch-ribbon-cutting")) == "2022-09-29"  # "\| Sep 29, 2022 11:30:10 AM"
    assert published_date(_page_at("04_2026-08-27_rebaseline", "newsroom-first-time-homebuyers-get-a-boost-dupaco-offers-fhlb-hometart-grants")) == "2026-01-05"  # "\| Jan 5, 2026 8:48:33 AM"
    assert published_date(_page("newsroom-dupaco-community-credit-union-branch-office-to-open-in-coralville-iowa")) == "2021-10-08"  # "\| Oct 8, 2021 12:57:34 PM"
    assert published_date(_page("learn-blog-as-vehicle-costs-continue-to-rise")) == "2025-04-16"  # front matter, then "| Apr 16, 2025 11:37:36 AM" on line 10

def test_published_date_window_has_slack():  # Task 11 review: 367 and 364 prose pages in crawls 01 and 02 date on line 6
    assert published_date("\n".join(["x"] * 9 + ["April 06, 2026"])) == "2026-04-06"  # line 10
    assert published_date("\n".join(["x"] * 10 + ["April 06, 2026"])) is None  # line 11 lies outside the window

def test_select_dated_newest_publication_per_key():
    fs = [_count("23 branch office locations", "2026-03-17"), _count("22 branch office locations", "2026-05-05"),
          _count("24 branch office locations", "2024-08-09", authority=0)]
    assert [f.value_text for f in select_dated(fs, None)] == ["22 branch office locations"]
    assert [f.value_text for f in select_dated(fs, "2026-03-31")] == ["23 branch office locations"]
    assert [f.value_text for f in select_dated(fs, "2024-08-31")] == ["24 branch office locations"]
    assert select_dated(fs, "2021-01-01") == []

def test_publication_beats_authority():
    blog = _count("22 branch office locations", "2026-05-05", authority=0, url="https://www.dupaco.com/learn/blog/b")
    news = _count("23 branch office locations", "2026-04-06", authority=1)
    assert select_dated([news, blog], None) == [blog]

def test_status_at_and_cutoff():
    hy = make_fact("branch", "closure_date", "March 31, 2026", extractor="prose", claim=ClaimType.STATUS,
                   event="2026-03-31", published="2025-06-20", branch_name="hy-vee")
    assert [status_at(hy, d) for d in ("2026-03-01", "2026-03-31", "2026-04-01")] == ["scheduled", "scheduled", "closed"]
    assert cutoff("2026-05-31", 2022, False) == "2022-12-31" and cutoff(None, 2024, True) is None and cutoff("2025-01-01", None, False) == "2025-01-01"


# Task 6 pins beyond the brief's six: the front-matter count and byline forms on their own, the resolver hookup, the
# year filter and order, ruling (c) (no earliest-crawl caveat on dated plans) and the crawl 03 hours the byline dates.
from kb.question import Query, parse
from kb.registry import Registry
from kb.resolve import _EXACT_SLOTS, EARLIEST_NOTE, resolve
from kb.store import FactStore
from kb.tiers import QUALIFIER_FILTERS, misses, select_tier
R = Registry.load()
C01, C03, C05 = "01_2026-05-12_baseline", "03_2026-06-09_recrawl", "05_2026-09-28_latest"
NNBSP = chr(0x202F)  # the narrow no-break space crawl 04's car-deal byline prints before "PM"

def test_published_date_counts_lines_after_a_front_matter_block():  # ruling (b): the line after the closing --- is line 1
    front = ["---", "title: Costs rise | Dupaco", "description: As of December 2024, prices rose.", "---"]
    head = ["", "[Personal Resources ](https://www.dupaco.com/learn/blog)", "", "# Costs rise", "", "x", "x", "x", "x",
            " Written by [A Writer](https://www.dupaco.com/learn/blog/author/a-writer) | Apr 16, 2025 11:37:36 AM"]
    assert published_date("\n".join(front + head)) == "2025-04-16"  # file line 14, the 10th after the closing ---
    assert published_date("\n".join(front[1:] + head)) is None  # no opening ---: no front matter, and line 13 is outside
    assert published_date("\n".join(["---"] + head[1:])) == "2025-04-16"  # never closed: counted from line 1 (line 10)
    assert published_date("\n".join(["---"] + head)) is None  # line 11

def test_byline_forms():  # ruling (b): "\|" or "|", a full or abbreviated month, an optional comma after the year, a time
    by = "Written by [A Writer](https://www.dupaco.com/newsroom/author/a-writer) {}"
    read = {"\\| Sep 29, 2022 11:30:10 AM": "2022-09-29", "| Oct 8, 2021": "2021-10-08", "| Sept 29, 2022": "2022-09-29",
            "\\| Aug 10, 2026, 6:14:28" + NNBSP + "PM": "2026-08-10", "| September 29, 2022, 11:30 AM": "2022-09-29",
            "| Apr 16, 2025 11:37:36 AM": "2025-04-16"}  # "Apr": lexicon.MONTHS has no bare "apr" (the APR)
    assert {tail: published_date(by.format(tail)) for tail in read} == read
    for tail in ("| Feb 30, 2024", "| Sep 29, 22", "| Sep 29, 2022 soon", "Sep 29, 2022"):  # the last: no pipe, no byline
        assert published_date(by.format(tail)) is None, tail
    assert published_date("Posted by [A Writer](https://www.dupaco.com/a) | Sep 29, 2022") is None
    assert published_date(_page_at("04_2026-08-27_rebaseline", "learn-blog-how-to-get-a-good-deal-on-a-car")) == "2026-08-10"

def _store(*crawls):
    s = FactStore()
    for sid, facts in crawls:
        s.add(sid, sid[3:13], facts)
    s.finalize(); return s

def _ask(as_of=None, intent="count", **slots):
    return Query(intent, "branch_count", "count", tuple(sorted(slots.items())), as_of, False, "How many branches?", frozenset(), "")

def _texts(store, as_of=None, **slots):
    p = resolve(_ask(as_of, **slots), store, R)
    return [f.value_text for f in p.facts] if p.confident else None

def test_dated_pools_select_by_publication_up_to_the_asked_date():  # Review Focus 3 on a synthetic store
    def crawl(sid, *extra):
        return sid, [_count("23 branch office locations", "2026-04-06", snapshot_id=sid),
                     _count("24 branch office locations", "2024-08-09", snapshot_id=sid)] + list(extra)
    blog = _count("22 branch office locations", "2026-05-05", authority=0, url="https://www.dupaco.com/learn/blog/b", snapshot_id=C05)
    store = _store(crawl(C01), crawl(C05, blog))
    assert _texts(store) == ["22 branch office locations"]  # publication beats authority (current() kept the newsroom's 23)
    assert _texts(store, "2026-06-01") == ["23 branch office locations"]  # crawl 01 is in force and holds no 22
    assert _texts(store, "2024-08-31") == ["24 branch office locations"]  # before the first crawl the asked date still cuts
    assert _texts(store, "2021-01-01") is None  # nothing published by then: refused
    assert _texts(store, year=2024) == ["24 branch office locations"]  # a year no fact carries cuts at its last day
    assert resolve(_ask("2024-08-31"), store, R).conflict_note is None  # ruling (c): a dated plan carries no caveat
    change = resolve(_ask("2024-08-31", intent="change"), store, R)  # the asked date cuts the "from" side only
    assert [(f.source.snapshot_id, f.value_text) for f in change.facts] == [
        (C01, "24 branch office locations"), (C05, "22 branch office locations")] and change.conflict_note is None

def test_year_scoped_facts_filter_by_year_instead_of_cutting():
    store = _store((C05, [_count("1,000 employees", "2024-02-01", year=2023, snapshot_id=C05),
                          _count("1,100 employees", "2025-03-01", year=2024, snapshot_id=C05)]))
    assert _texts(store) == ["1,100 employees", "1,000 employees"]  # every year on file, newest first (user decision 2)
    assert _texts(store, year=2023) == ["1,000 employees"]  # published in 2024: the year filters, it does not cut
    assert _texts(store, year=2022) is None  # hard: no fact describes 2022
    assert _texts(store, "2024-12-31") == ["1,000 employees"]  # the asked date still cuts by publication

def test_year_filter_is_hard_and_orders_newest_first():
    fs = [_count("1,000 employees", "2024-02-01", year=2023), _count("1,100 employees", "2025-03-01", year=2024)]
    year = QUALIFIER_FILTERS["year"]
    assert year(fs, _ask(year=2023)) == fs[:1] and year(fs, _ask()) == fs
    assert misses(_ask(year=2022), fs) and not misses(_ask(year=2022), [_count("22 branch office locations", "2026-05-05")])
    named = [_count("x", "2024-01-01", year=2023, branch_name="a"), _count("y", "2025-01-01", year=2024, branch_name="b")]
    assert [f.value_text for f in select_tier(named, _ask())] == ["y", "x"]  # the year orders before the branch name
    programs = [_count("p", "2025-01-01", year=2024, program="b"), _count("q", "2024-01-01", year=2023, program="a")]
    assert [f.value_text for f in select_tier(programs, _ask())] == ["q", "p"]  # and after the program
    assert "year" in _EXACT_SLOTS

def test_dated_answers_before_the_first_crawl_carry_no_caveat(store_full, ks_full):  # ruling (c); user decision 1
    question = "What are the lobby hours at the Platteville branch?"
    p = resolve(parse(question, "2026-01-15", R), store_full, R)
    assert p.confident and p.snapshot_id == C01 and {f.published_date for f in p.facts} == {"2021-07-23"}
    assert p.conflict_note is None
    a = ks_full.answer(question, "2026-01-15")
    assert "8:30 a.m.–5 p.m." in a.text and EARLIEST_NOTE not in a.text and EARLIEST_NOTE not in (a.conflict_note or "")
    assert resolve(parse(question, "2021-07-22", R), store_full, R).confident is False  # published the next day
    assert ks_full.answer("What is the APY on the 10-month certificate special?", "2026-01-15").text.endswith(EARLIEST_NOTE)  # (pin)

def test_bylines_date_crawl_03s_mineral_point_road_hours(store_full):  # brief Step 4: crawl 03's hours facts, 36 -> 40
    pa = store_full.by_product_attr[C03]
    lobby, drive = pa.get(("branch", "lobby_hours"), []), pa.get(("branch", "driveup_hours"), [])
    assert (len(lobby), len(drive)) == (21, 19)
    mpr = sorted((f.attribute, dict(f.qualifiers)["day"], f.value_text, f.published_date) for f in lobby + drive
                 if dict(f.qualifiers)["branch_name"] == "mineral point road, madison")
    assert mpr == [("driveup_hours", "monday-friday", "9 a.m.-5 p.m.", "2022-09-29"), ("driveup_hours", "saturday-sunday", "Closed", "2022-09-29"),
                   ("lobby_hours", "monday-friday", "9 a.m.-5 p.m.", "2022-09-29"), ("lobby_hours", "saturday-sunday", "Closed", "2022-09-29")]
