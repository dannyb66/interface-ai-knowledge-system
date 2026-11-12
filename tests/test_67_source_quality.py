"""Raw source identity remains available after canonical grouping."""
from dataclasses import asdict

from contract import Page, Snapshot
from kb.conflicts import ConflictBook, parse_curated
from kb.prose_facts import ProseBook, parse_prose
from kb.registry import Registry
from kb.source_pages import SourcePages, content_digest, source_page

SID = "05_2026-09-28_latest"
BASE = "https://www.dupaco.com/online-and-mobile-banking/mobile-payments"
TEXT = "A mobile wallet stores payment cards on your device."


def book():
    return ProseBook(parse_prose({"_version": "test", "facts": [{
        "canonical_urls": [BASE], "crawls": [SID], "quote": TEXT, "product_id": "mobile_wallet",
        "attribute": "description", "qualifiers": {}, "value": None, "value_text": TEXT, "unit": "text",
        "claim_type": "assertion", "published_date": None, "event_date": None, "extractor": "curated"}]}, Registry.load()))


def test_content_hash_has_one_documented_newline_rule():
    assert content_digest("A\r\nB\r") == content_digest("A\nB\n")
    assert content_digest("A  B") != content_digest("A B")


def test_failed_rendered_counters_are_not_confused_with_free_fees():
    from kb.source_quality import quality_reason
    assert quality_reason("Assets NaN", "text", "organization_fact")
    assert quality_reason("Members 0+", "count", "organization_fact")
    assert quality_reason("Branches: 0", "count", "organization_fact")
    assert quality_reason("The fee is $0.", "usd", "fee") is None
    assert quality_reason("Free for members", "free", "fee") is None
    assert quality_reason("No branches closed this year: 0 closures.", "count", "organization_fact") is None


def test_canonical_variants_verify_the_actual_raw_page_and_keep_order():
    good = source_page(SID, BASE + "?hsLang=en", TEXT)
    other = source_page(SID, BASE + "?hsLang=other", "An unrelated statement.")
    first = book().facts(SID, SourcePages([other, good]))
    second = book().facts(SID, SourcePages([good, other]))
    assert first == second and len(first) == 1
    assert first[0].source.url == good.raw_url
    assert first[0].source.citation_url == good.raw_url
    assert first[0].source.page_id == good.page_id
    assert first[0].source.content_sha256 == content_digest(TEXT)


def test_conflicting_same_raw_capture_is_quarantined_without_pin():
    one = source_page(SID, BASE, TEXT, fetched_at="2026-09-28")
    two = source_page(SID, BASE, "A conflicting capture.", fetched_at="2026-09-28")
    pages = SourcePages([one, two])
    assert pages.summary()["ambiguous_raw_variants"] == 2
    assert book().facts(SID, pages) == []


def test_source_verification_cannot_relabel_another_crawls_page():
    from kb.claim_semantics import SourcePin
    from kb.source_pages import matching

    old = source_page("04_2026-08-27_rebaseline", BASE, TEXT)
    pages = SourcePages([old])
    assert book().facts(SID, pages) == []
    # A declared pin cannot turn an old-crawl record into current evidence either.
    pin = SourcePin(SID, BASE, old.content_sha256)
    assert matching(pages, BASE, SID, TEXT, {}, pins=[pin]) == ()


def test_other_crawls_do_not_make_a_current_capture_ambiguous():
    old = source_page("04_2026-08-27_rebaseline", BASE, "An old description.", fetched_at="unchanged")
    current = source_page(SID, BASE, TEXT, fetched_at="unchanged")
    pages = SourcePages([old, current])
    assert not pages.ambiguous(current)
    facts = book().facts(SID, pages)
    assert len(facts) == 1 and facts[0].source.page_id == current.page_id


def test_runtime_ingestion_and_raw_citation_are_manifest_order_independent():
    import solution
    pages = [Page(BASE + "?hsLang=en", "Wallet", TEXT, "2026-09-28"),
             Page(BASE + "?hsLang=other", "Other", "An unrelated statement.", "2026-09-28")]
    answers = []
    for order in (pages, list(reversed(pages))):
        ks = solution.build(); ks._prose_book = book(); ks._book = ConflictBook(())
        ks.ingest(Snapshot(SID, "2026-09-28", order))
        answer = ks.answer("What is a mobile wallet?")
        assert answer.confident and answer.sources[0].url == pages[0].url
        assert answer.sources[0].quote == TEXT
        answers.append(asdict(answer))
    assert answers[0] == answers[1]


def test_conflict_verification_cannot_borrow_a_different_raw_variants_quote():
    url1, url2 = BASE + "?hsLang=en", BASE + "?hsLang=other"
    rows = {"conflicts": [{"topic": "example", "values": ["1%", "2%"], "resolution": "2%",
                           "reason": "newer", "confidence": 1, "sources": [
                               {"url": url1, "snapshot_id": SID, "value": "1%", "quote": "One is 1%."},
                               {"url": url1, "snapshot_id": SID, "value": "2%", "quote": "Two is 2%."}]}]}
    conflict = ConflictBook(parse_curated(rows))
    pages = SourcePages([source_page(SID, url1, "One is 1%."), source_page(SID, url2, "Two is 2%.")])
    conflict.observe(SID, pages)
    assert conflict.emit() == []

    old_only = SourcePages([source_page("04_2026-08-27_rebaseline", url1, "One is 1%. Two is 2%.")])
    conflict.observe(SID, old_only)
    assert conflict.emit() == []
