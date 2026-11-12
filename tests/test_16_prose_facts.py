import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kb.prose_facts import ProseBook, load_prose, parse_prose
from kb.registry import Registry

R = Registry.load()
SID = "05_2026-09-28_latest"
WALLET = {
    "canonical_urls": ["https://www.dupaco.com/online-and-mobile-banking/mobile-payments"], "crawls": [SID],
    "quote": "Your Dupaco debit and credit cards are compatible with Apple Pay, Google Pay and Samsung Pay.",
    "product_id": "mobile_wallet", "attribute": "description", "qualifiers": {}, "value": None,
    "value_text": "Your Dupaco debit and credit cards are compatible with Apple Pay, Google Pay and Samsung Pay.",
    "unit": "text", "claim_type": "assertion", "published_date": None, "event_date": None, "extractor": "curated",
}


def _parse(*entries):
    return parse_prose({"_version": "test", "facts": list(entries)}, R)


def _system(tmp_path, facts, snaps):
    import solution
    shutil.copytree("submission/data", tmp_path / "data")
    (tmp_path / "data/prose_facts.json").write_text(json.dumps({"_version": "t", "facts": facts}))
    ks = solution.build(data_dir=tmp_path / "data")
    for snapshot in snaps:
        ks.ingest(snapshot)
    return ks


def test_verified_entry_becomes_a_curated_fact(tmp_path, real_snapshots):
    ks = _system(tmp_path, [WALLET], real_snapshots)
    fs = ks.store.by_product_attr[SID][("mobile_wallet", "description")]
    assert [(f.value_text, f.extractor, f.source.canonical_url) for f in fs] == [(WALLET["value_text"], "curated", WALLET["canonical_urls"][0])]
    assert ("mobile_wallet", "description") not in ks.store.by_product_attr[real_snapshots[0].snapshot_id]


def test_missing_quote_drops_and_logs(tmp_path, real_snapshots, capsys):
    bad = {**WALLET, "quote": "Your Dupaco cards work with every wallet.", "value_text": "Your Dupaco cards work with every wallet."}
    ks = _system(tmp_path, [bad], real_snapshots)
    assert ("mobile_wallet", "description") not in ks.store.by_product_attr[SID]
    assert "KB-E08" in capsys.readouterr().err


def test_a_listed_page_without_the_quote_is_never_cited(tmp_path, real_snapshots, capsys):
    extra = {**WALLET, "canonical_urls": WALLET["canonical_urls"] + ["https://www.dupaco.com/rates"]}
    fs = _system(tmp_path, [extra], real_snapshots).store.by_product_attr[SID][("mobile_wallet", "description")]
    assert [f.source.canonical_url for f in fs] == WALLET["canonical_urls"]
    assert "KB-E08" in capsys.readouterr().err


@pytest.mark.parametrize("change", [
    {"attribute": "apy"}, {"value_text": "Venmo"},
    {"quote": "Earn 2.25% APY with Apple Pay.", "value_text": "Apple Pay"},
    {"qualifiers": {"colour": 1}}, {"canonical_urls": []}, {"published_date": "2025-02-30"},
    {"value_text": "Apple Pay is available to 25 people.", "quote": "Only 25 other people use Venmo."},
    {"value": float("nan")}, {"value": float("inf")}, {"value": 25}, {"unit": "usd"},
])
def test_parse_prose_rejects_bad_entries(change):
    with pytest.raises(ValueError, match="mobile_wallet"):
        _parse({**WALLET, **change})


def test_numeric_prose_requires_value_and_unit_to_match_its_text():
    entry = next(e for e in json.loads(Path("submission/data/prose_facts.json").read_text())["facts"]
                 if e["product_id"] == "shared_branching" and e["attribute"] == "count")
    for change in ({"value": 42}, {"unit": "usd"}, {"value": None}):
        with pytest.raises(ValueError, match="shared_branching"):
            _parse({**entry, **change})


def test_disjoint_crawl_source_sets_preserve_history_but_overlap_is_rejected():
    old = {**WALLET, "crawls": ["01_2026-05-12_baseline"]}
    newer = {**WALLET, "canonical_urls": WALLET["canonical_urls"] + ["https://www.dupaco.com/mobile-payments"]}
    assert len(_parse(old, newer)) == 2
    with pytest.raises(ValueError, match="duplicate"):
        _parse(newer, copy.deepcopy(newer))


def test_required_facts_and_crawl_specific_eligibility(ks_full):
    from kb.temporal import select_dated
    latest = ks_full.store.by_product_attr[SID]
    elig = sorted(latest[("membership", "eligibility")], key=lambda f: dict(f.qualifiers)["item"])
    text = " ".join(dict.fromkeys(f.value_text for f in elig))
    assert "If Any of These Sound Like You" in text
    for condition in ("live or work within our charter area", "immediate family member", "Rural Ideas Network",
                      "open a savings account with $25 or more", "keep at least $25 in your savings account"):
        assert condition in text
    from kb.claim_groups import complete_groups
    assert all(f.claim_groups for f in elig) and complete_groups(elig)
    assert {f.value_text for f in select_dated(latest[("forbes_recognition", "description")], None)} == {"This was the fifth time Forbes recognized Dupaco."}
    for pid, attr in (("mobile_wallet", "description"), ("student_loans", "description"), ("home_start", "description"), ("shared_branching", "count"), ("home_start", "eligibility"), ("mortgage_rate_relief", "eligibility")):
        assert latest.get((pid, attr)), pid
    old = ks_full.store.by_product_attr["01_2026-05-12_baseline"][("membership", "eligibility")]
    assert any("charter area or have" in f.value_text for f in old)


def test_every_curated_triple_verifies():
    result = subprocess.run([sys.executable, "scripts/check_prose_facts.py"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("prose: ") and "verified" in result.stdout


def test_description_coverage_at_least_80_percent(ks_full):
    products = {p for p in R.aliases().values() if R.published(p) & {"description", "eligibility"}}
    latest = ks_full.store.by_product_attr[SID]
    covered = {p for p, a in latest if a in ("description", "eligibility") and any(f.extractor == "curated" for f in latest[(p, a)])}
    assert len(covered & products) / len(products) >= .80


def test_book_requires_actual_quote_and_reports_dropped():
    book = ProseBook(_parse(WALLET))
    assert book.pages_needed(SID) == frozenset(WALLET["canonical_urls"])
    assert book.facts(SID, {}) == []
    assert len(book.dropped([SID])) == 1


def test_ingest_normalizes_shared_conflict_and_prose_pages_once(real_snapshots, monkeypatch):
    import solution
    from kb import conflicts, prose_facts
    from kb.system import _page_text
    ks = solution.build()
    snapshot = next(s for s in real_snapshots if s.snapshot_id == SID)
    overlap = ks._book.pages_needed(SID) & ks._prose_book.pages_needed(SID)
    texts = sorted((_page_text(p) for p in snapshot.pages), key=lambda t: (t[3], t[0]))
    raw = {}
    for _, markdown, url, _ in texts:
        if url in overlap:
            raw.setdefault(url, markdown)
    assert raw and set(raw) == overlap
    calls = {markdown: 0 for markdown in raw.values()}
    original = prose_facts.page_text
    def counted(markdown):
        if markdown in calls:
            calls[markdown] += 1
        return original(markdown)
    monkeypatch.setattr(prose_facts, "page_text", counted)
    monkeypatch.setattr(conflicts, "page_text", counted)
    ks.ingest(snapshot)
    assert set(calls.values()) == {1}
    assert ks.store.by_product_attr[SID][("forbes_recognition", "description")]
