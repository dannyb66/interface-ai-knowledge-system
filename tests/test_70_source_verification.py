"""Raw-source identity checks use synthetic pages, independent of eval gold."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_prose_facts import verify_entries
from phase4_sources import source_records
from kb.claim_semantics import SourcePin
from kb.prose_facts import ProseEntry
from kb.source_pages import SourcePages, source_page
from kb.types import ClaimType

SID = "05_2026-09-28_latest"
URL = "https://www.example.test/product"
QUOTE = "Members can manage their savings online."


def entry(pages=(), **changes):
    value = ProseEntry((URL,), (SID,), QUOTE, "example", "description", (), None,
                       QUOTE, "text", ClaimType.ASSERTION, None, None, "curated",
                       source_pins=tuple(SourcePin(p.snapshot_id, p.raw_url, p.content_sha256) for p in pages))
    return replace(value, **changes)


def report(value, *pages):
    return verify_entries([value], {SID: SourcePages(pages)})


def test_legacy_canonical_accounting_preserves_raw_aliases():
    one = source_page(SID, URL, QUOTE)
    two = source_page(SID, URL + "/", QUOTE)
    result = report(entry(), one, two)
    assert (result["verified"], result["total"]) == (1, 1)
    assert result["failures"] == []


def test_v2_requires_every_quote_bearing_raw_variant():
    one = source_page(SID, URL, QUOTE)
    two = source_page(SID, URL + "/", QUOTE + " More details.")
    assert report(entry([one]), one, two)["failures"]
    result = report(entry([one, two]), one, two)
    assert result["failures"] == []
    assert result["verified_pins"] == result["total_pins"] == 2


def test_correct_quote_on_other_alias_does_not_rescue_bad_pin():
    original = source_page(SID, URL, QUOTE)
    alias = source_page(SID, URL + "/", QUOTE)
    changed = source_page(SID, URL, "A different statement.")
    assert report(entry([original, alias]), changed, alias)["failures"]


def test_unpinned_ambiguous_raw_source_fails_but_exact_pins_can_verify():
    one = source_page(SID, URL, QUOTE)
    two = source_page(SID, URL, QUOTE + " More details.")
    assert report(entry(), one, two)["failures"]
    assert not report(entry([one, two]), one, two)["failures"]


def test_omitted_canonical_copy_is_reported():
    one = source_page(SID, URL, QUOTE)
    two = source_page(SID, URL + "-other", QUOTE)
    assert "omitted=" in report(entry([one]), one, two)["failures"][0]


def test_publication_is_checked_on_each_raw_variant():
    one = source_page(SID, URL, "# News\nSeptember 1, 2026\n\n" + QUOTE)
    two = source_page(SID, URL + "/", "# News\nSeptember 2, 2026\n\n" + QUOTE)
    result = report(entry([one, two], published_date="2026-09-01"), one, two)
    assert any("publication date differs" in f for f in result["failures"])


def test_source_loader_preserves_aliases_and_normalizes_only_line_endings(tmp_path):
    root = tmp_path / SID
    root.mkdir()
    (root / "a.md").write_bytes((QUOTE + "\r\n").encode())
    (root / "b.md").write_bytes((QUOTE + "\n").encode())
    meta = {"snapshot_id": SID, "pages": [
        {"url": URL, "file": "a.md"}, {"url": URL + "/", "file": "b.md"}]}
    (root / "manifest.json").write_text(json.dumps(meta))
    records = source_records(tmp_path)
    assert len(records) == 2
    assert records[0].page.content_sha256 == records[1].page.content_sha256
    assert records[0].page.raw_url != records[1].page.raw_url


def test_source_loader_rejects_manifest_path_escape(tmp_path):
    root = tmp_path / SID
    root.mkdir()
    (tmp_path / "outside.md").write_text(QUOTE)
    (root / "manifest.json").write_text(json.dumps({"snapshot_id": SID, "pages": [
        {"url": URL, "file": "../outside.md"}]}))
    with pytest.raises(ValueError):
        source_records(tmp_path)


def test_fee_effective_date_cannot_be_omitted_or_borrowed_from_a_different_schedule():
    page = source_page(SID, URL, "Effective August 1, 2026\n" + QUOTE)
    fee = entry([page], attribute="fee", semantics=SimpleNamespace(role="fee"))
    assert any("effective date" in f for f in report(fee, page)["failures"])
    assert report(replace(fee, effective_date="2025-08-01"), page)["failures"]
    assert not report(replace(fee, effective_date="2026-08-01"), page)["failures"]


def test_dated_v2_census_does_not_borrow_identical_words_from_other_publication():
    old = source_page(SID, URL + "-old", "January 1, 2025\n" + QUOTE)
    new = source_page(SID, URL, "January 1, 2026\n" + QUOTE)
    dated = entry([new], published_date="2026-01-01", semantics=SimpleNamespace(role="description"))
    assert not report(dated, old, new)["failures"]
    # Wrong-date pin cannot be rescued by the correct quote on the new source.
    bad = replace(dated, source_pins=(SourcePin(SID, new.raw_url, old.content_sha256),))
    assert report(bad, old, new)["failures"]
    # V1 still reports omitted copies across all publication contexts.
    assert report(entry(), old, new)["failures"]
