"""Offline review expansion must preserve source identities and complete statements."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_reviewed_candidates import build, expand, write_catalog
import json
from kb.claim_semantics import parse_pins, semantic_revision
from kb.source_pages import SourcePages, source_page


def seed():
    quote = "Account access is free for members only."
    return {"quote": quote, "value_text": quote, "effective_date": "2026-08-01",
            "semantics": {"claim_id": "account.access", "revision": "pending"}}


def test_expansion_preserves_exact_aliases_and_crawl_dependent_url_sets():
    first = source_page("first", "https://example.test/account", seed()["quote"])
    alias = source_page("first", "https://example.test/account/", seed()["quote"])
    second = source_page("second", "https://example.test/new-account", seed()["quote"])
    entries = expand(seed(), {"first": SourcePages([alias, first]), "second": SourcePages([second])})
    assert len(entries) == 2
    assert sorted(len(e["source_pins"]) for e in entries) == [1, 2]
    for entry in entries:
        pins = parse_pins(entry["source_pins"], entry["crawls"], entry["canonical_urls"])
        assert entry["semantics"]["revision"] == semantic_revision(
            entry["quote"], entry["value_text"], pins, entry["effective_date"])
        assert entry["quote"] == entry["value_text"] == seed()["quote"]


def test_order_is_independent_and_bad_variant_is_not_pinned():
    good = source_page("first", "https://example.test/account", seed()["quote"])
    other = source_page("first", "https://example.test/account/", "A different account.")
    assert expand(seed(), {"first": SourcePages([good, other])}) == expand(seed(), {"first": SourcePages([other, good])})
    assert len(expand(seed(), {"first": SourcePages([good, other])})[0]["source_pins"]) == 1


def test_absent_statement_is_not_synthesized():
    with pytest.raises(ValueError, match="no source"):
        expand(seed(), {"first": SourcePages([])})


def test_replay_cannot_add_a_crawl_outside_reviewed_scope():
    a = source_page("first", "https://example.test/account", seed()["quote"])
    b = source_page("second", "https://example.test/account", seed()["quote"])
    result = expand({**seed(), "crawls": ["first"]}, {"first": SourcePages([a]), "second": SourcePages([b])})
    assert result[0]["crawls"] == ["first"]


def test_changed_publication_context_splits_crawl_groups():
    old = source_page("first", "https://example.test/account", "January 1, 2025\n" + seed()["quote"])
    new = source_page("second", "https://example.test/account", "January 1, 2026\n" + seed()["quote"])
    dated = {**seed(), "published_date": "2026-01-01"}
    entries = expand(dated, {"first": SourcePages([old]), "second": SourcePages([new])})
    assert {(e["published_date"], tuple(e["crawls"])) for e in entries} == {
        ("2025-01-01", ("first",)), ("2026-01-01", ("second",))}


def test_generic_quote_in_two_dated_contexts_requires_review():
    old = source_page("first", "https://example.test/a", "January 1, 2025\n" + seed()["quote"])
    new = source_page("first", "https://example.test/b", "January 1, 2026\n" + seed()["quote"])
    with pytest.raises(ValueError, match="publication contexts"):
        expand({**seed(), "published_date": "2026-01-01"}, {"first": SourcePages([old, new])})


def test_required_claim_groups_survive_build_and_serialization(tmp_path):
    group = {"entity": "program", "attribute": "eligibility", "claim_set": "requirements",
             "crawls": ["first"], "required_claim_ids": ["missing.caveat"]}
    result = build([], {"facts": [], "claim_groups": [group]}, {}, [group])
    assert result["claim_groups"] == [group]
    path = tmp_path / "catalog.json"
    write_catalog(path, result)
    assert json.loads(path.read_text())["claim_groups"] == [group]


def test_reviewed_publication_scope_is_build_time_only_and_cannot_relabel_sources():
    old = source_page("first", "https://example.test/a", "January 1, 2025\n" + seed()["quote"])
    new = source_page("first", "https://example.test/b", "January 1, 2026\n" + seed()["quote"])
    scoped = {**seed(), "published_date": "2026-01-01", "_publication_scope": "2026-01-01"}
    result = expand(scoped, {"first": SourcePages([old, new])})
    assert result[0]["canonical_urls"] == [new.canonical_url]
    assert "_publication_scope" not in result[0]
    with pytest.raises(ValueError, match="publication scope"):
        expand({**scoped, "_publication_scope": "2025-01-01"}, {"first": SourcePages([old, new])})


def test_replay_preserves_reviewed_group_order_and_bytes(tmp_path):
    later = {"entity": "z_program", "attribute": "eligibility", "claim_set": "z_requirements",
             "crawls": ["first"], "required_claim_ids": ["z.caveat"]}
    earlier = {"entity": "a_program", "attribute": "description", "claim_set": "a_procedure",
               "crawls": ["first"], "required_claim_ids": ["a.step"]}
    first = build([], {"facts": [], "claim_groups": [later, earlier]}, {})
    replay = build([], {"facts": []}, {}, first["claim_groups"])
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    write_catalog(before, first)
    write_catalog(after, replay)
    assert replay["claim_groups"] == [later, earlier]
    assert before.read_bytes() == after.read_bytes()
