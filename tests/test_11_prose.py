# tests/test_11_prose.py
from pathlib import Path
from kb.blocks import load_boilerplate, split_blocks
from kb.extract_rules import SourceContext
from kb.question import parse
from kb.registry import Registry
from kb.tiers import QUALIFIER_FILTERS
from kb.types import ClaimType, Fact, Source, make_key
R = Registry.load()
S01, S05 = "01_2026-05-12_baseline", "05_2026-09-28_latest"
BRANCHES = {"cedar rapids", "platteville", "grimes", "cedar falls", "waukee", "east washington, madison", "mineral point road, madison"}


def make_fact(product_id, attribute, value_text, *, snapshot_id="05_2026-09-28_latest", url="https://www.dupaco.com/rates",
              page_type="rate_sheet", authority=3, extractor="rules", claim=ClaimType.RATE, published=None, event=None,
              block=0, row=0, value=None, unit="pct", **quals):
    """Task 3's ``conftest.make_fact`` (same keywords and defaults), local until that helper lands in conftest."""
    key = make_key(product_id, attribute, quals)
    src = Source(url, url, page_type, authority, snapshot_id, "2026-09-28", block, row, "| row |")
    return Fact(key, product_id, attribute, key[2], value, value_text, unit, claim, None, event, published, src, extractor, 1.0)


def _facts(store, sid, attr): return store.by_product_attr[sid].get(("branch", attr), [])
def _rows(store, sid, attr, branch):
    fs = sorted((f for f in _facts(store, sid, attr) if dict(f.qualifiers)["branch_name"] == branch), key=lambda f: f.source.row_idx)
    return [(dict(f.qualifiers)["day"], f.value_text) for f in fs]

def test_hours_facts_per_branch_and_kind(store_full):
    for sid in (S01, S05):
        lobby, drive = _facts(store_full, sid, "lobby_hours"), _facts(store_full, sid, "driveup_hours")
        assert (len(lobby), len(drive)) == (21, 19)
        assert {dict(f.qualifiers)["branch_name"] for f in lobby} == BRANCHES
        assert all(f.extractor == "prose" and f.published_date and f.claim_type is ClaimType.ASSERTION for f in lobby + drive)

def test_platteville_hours_values(store_full):
    assert _rows(store_full, S05, "lobby_hours", "platteville") == [
        ("monday-thursday", "8:30 a.m.–5 p.m."), ("friday", "8:30 a.m.–5:30 p.m."), ("saturday", "9 a.m.–noon"), ("sunday", "Closed")]
    assert _rows(store_full, S05, "driveup_hours", "platteville") == [
        ("monday-friday", "8 a.m.–6 p.m."), ("saturday", "9 a.m.–noon"), ("sunday", "ATM only")]
    f = next(f for f in _facts(store_full, S05, "lobby_hours") if dict(f.qualifiers)["branch_name"] == "platteville")
    assert (f.published_date, f.source.canonical_url) == (
        "2021-07-23", "https://www.dupaco.com/newsroom/dupaco-community-credit-union-celebrates-completion-of-expanded-branch")

def test_cedar_rapids_split_headers(store_full):  # "**Lobby**" alone on its line; ASCII hyphens as printed
    assert _rows(store_full, S05, "lobby_hours", "cedar rapids") == [
        ("monday-thursday", "8:30 a.m.-5 p.m."), ("friday", "8:30 a.m.-6 p.m."), ("saturday", "8:30 a.m.-12:30 p.m."), ("sunday", "Closed")]

def test_hours_scan_stops_at_the_about_caption(store_full):
    import re
    ok = re.compile(r"(?i)^(closed|atm only|\d{1,2}(:\d{2})? [ap]\.m\..*)$")
    facts = [f for a in ("lobby_hours", "driveup_hours") for f in _facts(store_full, S05, a)]
    assert facts and all(ok.match(f.value_text) for f in facts)  # "facts and": an empty store must not pass

def test_day_inside_a_range_selects_that_line():
    fs = [make_fact("branch", "lobby_hours", v, extractor="prose", claim=ClaimType.ASSERTION, unit="text", branch_name="x", day=d)
          for d, v in (("monday-thursday", "8:30 a.m.–5 p.m."), ("friday", "8:30 a.m.–6 p.m."), ("saturday-sunday", "Closed"))]
    day = QUALIFIER_FILTERS["day"]
    assert [f.value_text for f in day(fs, parse("What are the lobby hours on Wednesday?", None, R))] == ["8:30 a.m.–5 p.m."]
    assert [f.value_text for f in day(fs, parse("Lobby hours on Sunday?", None, R))] == ["Closed"]
    assert day(fs[:1], parse("What are the lobby hours on Friday?", None, R)) == fs[:1]  # soft: no line holds Friday


# The produced helpers, imported inside each test so the tests above fail on their own assertions first.
# _PAGE: the body ends at its about tail alone (lines 5-22). Line 22 is day-shaped but follows the footer caption, so it
# is no fact while the scan stops at the caption; the block after the tail is no fact while the tail ends the body.
_PAGE = "\n".join([
    "1 min read", "", "[A Writer](https://www.dupaco.com/newsroom/author/a-writer)", "April 06, 2026", "",
    "# Dupaco opens its newest branch", "", "GALENA, Ill.–Dupaco opened its newest branch this week.", "",
    "The phone number for the Oldenburg Lane branch is on the locator. Branch hours are:", "",
    "**Lobby**", "", "Monday–Friday: 9 a.m.–5 p.m.", "", "Saturday-Sunday: Closed", "",
    "**Drive-thru** Monday-Friday: 8 a.m.–6 p.m.", "",
    "**ABOUT DUPACO COMMUNITY CREDIT UNION:**", "", "Dupaco Community Credit Union is a member-owned cooperative.",
    "Saturday: 9 a.m.–noon", "", "Branch hours are:", "", "**Lobby** Sunday: Open"])
# _BARE: no footer, so the related-article line ({marker}, line 12) or the page end alone ends the body.
_BARE = "\n".join([
    "1 min read", "", "July 01, 2024", "", "# Dupaco opens a branch", "", "GRIMES, Iowa–Dupaco opened a branch.", "",
    "Branch hours are:", "", "**Lobby** Monday-Friday: 9 a.m.–5 p.m.", "", "{marker}", "",
    "June 07, 2022", "", "Branch hours are:", "", "**Lobby** Sunday: Open"])

def _ctx(page_type):
    url = "https://www.dupaco.com/newsroom/dupaco-opens-its-newest-branch"
    return SourceContext(url, url, page_type, 1, S05, "2026-09-28")

def test_day_labels_ranges_and_publication_dates():
    from pathlib import Path
    from kb.extract_prose import day_label
    from kb.temporal import published_date  # moved out of extract_prose (Task 6)
    from kb.tiers import day_range
    assert (day_label("Monday-Thursday"), day_label("Monday–Friday"), day_label("Sunday"), day_label("Lobby")) == (
        "monday-thursday", "monday-friday", "sunday", None)
    assert day_range("monday-thursday") == frozenset({"monday", "tuesday", "wednesday", "thursday"})
    assert day_range("saturday-sunday") == frozenset({"saturday", "sunday"}) and day_range("friday") == frozenset({"friday"})
    pages = Path("snapshots/05_2026-09-28_latest/pages")
    def page(prefix): return next(pages.glob(prefix + "*.md")).read_text(encoding="utf-8")
    assert published_date(page("newsroom-volunteering-pays-off-dupaco-credit-union-employees-reap-the-benefits-of-giving-b-bbbfc4")) == "2025-04-21"
    assert published_date(page("newsroom-dupaco-community-credit-union-celebrates-completion-of-expanded-branch")) == "2021-07-23"
    assert published_date(page("rates-59a9e6")) is None and published_date(_PAGE) == "2026-04-06"

def test_publication_dates_read_the_lexicon_month_table():  # one month table; a publication date spells its month out
    from kb import lexicon, temporal
    from kb.temporal import published_date
    assert temporal.MONTHS is lexicon.MONTHS
    full = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    assert [published_date("{} 5, 2024".format(month)) for month in full] == ["2024-{:02d}-05".format(n) for n in range(1, 13)]
    assert [published_date(text) for text in ("Sep 29, 2022", "Sept 29, 2022", "Jan 05, 2024", "February 30, 2024")] == [None] * 4

def test_prose_facts_need_a_dated_article_and_stay_in_its_body():
    from kb.extract_prose import EXTRACTOR, prose_facts
    from kb.temporal import article_body
    facts = prose_facts(_PAGE, _ctx("newsroom"), load_boilerplate())
    assert [(f.attribute, dict(f.qualifiers), f.value_text, f.source.row_idx, f.source.quote) for f in facts] == [
        ("lobby_hours", {"branch_name": "oldenburg lane, galena", "day": "monday-friday"}, "9 a.m.–5 p.m.", 13, "Monday–Friday: 9 a.m.–5 p.m."),
        ("lobby_hours", {"branch_name": "oldenburg lane, galena", "day": "saturday-sunday"}, "Closed", 15, "Saturday-Sunday: Closed"),
        ("driveup_hours", {"branch_name": "oldenburg lane, galena", "day": "monday-friday"}, "8 a.m.–6 p.m.", 17,
         "**Drive-thru** Monday-Friday: 8 a.m.–6 p.m.")]  # nothing from line 22 (after the caption) or after the tail
    assert all((f.extractor, f.unit, f.value, f.published_date, f.source.block_idx) == (EXTRACTOR, "text", None, "2026-04-06", -1)
               for f in facts)
    assert article_body(_PAGE.split("\n"), split_blocks(_PAGE, load_boilerplate())) == (5, 22)
    undated = _PAGE.replace("April 06, 2026", "")
    for markdown, page_type in ((_PAGE, "legacy_alias"), (_PAGE, "contact"), (_PAGE, "rate_sheet"), (undated, "newsroom")):
        assert prose_facts(markdown, _ctx(page_type), load_boilerplate()) == [], page_type

def test_each_body_boundary_alone():  # _BARE: a related-article line, each kind alone, else the page end
    from kb.extract_prose import prose_facts
    from kb.temporal import article_body
    for marker in ("## Recent News", "## Handpicked For You", "[Keep reading](https://www.dupaco.com/newsroom/a)", ""):
        page = _BARE.format(marker=marker)
        facts = [(f.value_text, f.source.row_idx) for f in prose_facts(page, _ctx("newsroom"), load_boilerplate())]
        assert article_body(page.split("\n"), split_blocks(page, load_boilerplate())) == (4, 11 if marker else 18), marker
        assert facts == [("9 a.m.–5 p.m.", 10)] + ([] if marker else [("Open", 18)]), marker

def test_article_bodies_end_before_related_articles(real_snapshots):  # crawls 01-03 head them "## Recent News"
    from kb.extract_prose import PROSE_PAGE_TYPES
    from kb.pagetype import classify
    from kb.temporal import article_body, published_date
    page = Path("snapshots/01_2026-05-12_baseline/pages/business-resources-10-tips-to-help-you-start-building-an-effective-"
                "social-media-strategy-6a2e97.md").read_text(encoding="utf-8")
    lines = page.split("\n")
    assert lines.index("## Recent News") == 106 and article_body(lines, split_blocks(page, load_boilerplate())) == (8, 105)
    for snapshot in real_snapshots:  # a related snippet's dateline ("June 07, 2022") never lies inside a body
        for p in snapshot.pages:
            if classify(p.url, p.markdown) in PROSE_PAGE_TYPES and published_date(p.markdown):
                lines = [line.rstrip("\r") for line in p.markdown.split("\n")]
                lo, hi = article_body(lines, split_blocks(p.markdown, load_boilerplate()))
                own = next((i for i, line in enumerate(lines) if published_date(line)), None)  # Task 6: a legacy byline,
                # the page's own date, sits under the H1, so inside the body; every other dated line stays out
                assert not [i for i in range(lo, hi + 1) if i != own and published_date(lines[i])], (snapshot.snapshot_id, p.url)

def _by_branch(store, sid, attr):
    return {dict(f.qualifiers)["branch_name"]: f for f in store.by_product_attr[sid].get(("branch", attr), [])}

def test_closure_and_alternative_facts(store_full):
    for sid in (S01, S05):
        c = _by_branch(store_full, sid, "closure_date")
        assert {k: (f.value_text, f.event_date, f.published_date, f.claim_type) for k, f in c.items()} == {
            "hy-vee": ("March 31, 2026", "2026-03-31", "2025-06-20", ClaimType.STATUS),
            "asbury": ("Oct. 1, 2024", "2024-10-01", "2024-06-06", ClaimType.STATUS)}
        assert {k: f.value_text for k, f in _by_branch(store_full, sid, "alternatives").items()} == {
            "hy-vee": "Key West and Sycamore Street", "asbury": "Pennsylvania Avenue and Northwest Arterial"}
        facts = [f for a in ("closure_date", "alternatives") for f in _facts(store_full, sid, a)]
        assert len(facts) == 4 and all((f.extractor, f.unit, f.value) == ("prose", "text", None) for f in facts)  # one each per article
        assert {f.claim_type for f in _facts(store_full, sid, "alternatives")} == {ClaimType.ASSERTION}

# _CLOSING: a closure article (the H1 names the branch) that also states hours; the sentence after the related-article
# heading (line 15) lies outside the body. The hours read the dateline's city, the closure the H1's branch.
_CLOSING = "\n".join([
    "2 min read", "", "[A Writer](https://www.dupaco.com/newsroom/author/a-writer)", "June 06, 2024", "",
    "# Dupaco closing Mullan Avenue branch, opens Key West drive-up", "",
    "DUBUQUE, Iowa—The Mullan Avenue branch’s last day of service will be Friday, Sept. 30, 2022.", "",
    "Members can access similar services at a [Dupaco full-service branch](https://www.dupaco.com/connect/branch-atm-locations/)"
    " at Key West—a short drive away. Branch hours are:", "", "**Lobby** Monday-Friday: 9 a.m.–5 p.m.", "",
    "## Handpicked for You", "", "This location will close March 31, 2026."])

def test_closure_facts_beside_hours_from_one_article():  # the Task 11 review's M2: prose_facts read hours alone
    from kb.extract_prose import prose_facts
    facts = prose_facts(_CLOSING, _ctx("newsroom"), load_boilerplate())
    assert [(f.attribute, dict(f.qualifiers).get("branch_name"), f.value_text, f.event_date, f.source.row_idx) for f in facts] == [
        ("lobby_hours", "dubuque", "9 a.m.–5 p.m.", None, 11), ("closure_date", "mullan avenue", "Sept. 30, 2022", "2022-09-30", 7),
        ("alternatives", "mullan avenue", "Key West", None, 9)]
    assert [(f.claim_type, f.published_date, f.source.quote) for f in facts[1:2]] == [
        (ClaimType.STATUS, "2024-06-06", "DUBUQUE, Iowa—The Mullan Avenue branch’s last day of service will be Friday, Sept. 30, 2022.")]
    for h1 in ("# Dupaco plans learning lab branch in Grimes", "# Dupaco celebrates Mullan Avenue branch"):  # no branch; no closure
        page = _CLOSING.replace("# Dupaco closing Mullan Avenue branch, opens Key West drive-up", h1)
        assert [f.attribute for f in prose_facts(page, _ctx("newsroom"), load_boilerplate())] == ["lobby_hours"], h1
    no_hours = _CLOSING.replace(" Branch hours are:", "")
    assert [f.attribute for f in prose_facts(no_hours, _ctx("newsroom"), load_boilerplate())] == ["closure_date", "alternatives"]
    bad_day = _CLOSING.replace("Sept. 30, 2022", "Sept. 31, 2022")  # no such day: no closure, the alternative stays
    assert [f.attribute for f in prose_facts(bad_day, _ctx("newsroom"), load_boilerplate())] == ["lobby_hours", "alternatives"]

def test_contact_reply_hours_never_become_branch_hours(store_full, ks_full):
    hours = _facts(store_full, S05, "lobby_hours") + _facts(store_full, S05, "driveup_hours")
    assert hours and {f.source.page_type for f in hours} == {"newsroom"}
    assert [f.source.canonical_url for f in store_full.by_product_attr[S05][("membership", "reply_hours")]] == [
        "https://www.dupaco.com/contact"]
    contact = "https://www.dupaco.com/contact"  # a dated contact page holding an hours block: its type alone stops them
    page = _PAGE.replace("# Dupaco opens its newest branch", "# Contact\n\nUse our form, and we’ll reply Monday–Friday, 8:30 a.m.–5:30 p.m.")
    facts = ks_full._page_facts((contact, page, contact, False), "2026-09-28", S05, {})
    assert [(f.product_id, f.attribute, f.value_text, f.source.page_type) for f in facts] == [
        ("membership", "reply_hours", "Monday–Friday, 8:30 a.m.–5:30 p.m.", "contact"),
        ("contact_page", "url", "https://www.dupaco.com/contact", "contact")]
