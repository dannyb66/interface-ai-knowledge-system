"""Source-only inventory guarantees, using tiny artificial pages."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("phase4_inventory", "scripts/phase4_inventory.py")
inventory_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory_module)


def make_snapshot(tmp_path, pages, snapshot_id="01_2026-01-01_test"):
    snapshot = tmp_path / snapshot_id
    snapshot.mkdir(exist_ok=True)
    manifest_pages = []
    for path, url, text in pages:
        target = snapshot / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        manifest_pages.append({"file": path, "url": url, "title": path, "fetched_at": "2026-01-01T00:00:00Z"})
    manifest = {"snapshot_id": snapshot_id, "taken_on": "2026-01-01", "pages": manifest_pages}
    (snapshot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return snapshot


def test_canonical_collisions_keep_raw_identity_and_content(tmp_path):
    make_snapshot(tmp_path, [("pages/a.md", "https://example.test/about?hsLang=en", "# About\nFirst source.\n"),
                             ("pages/b.md", "https://example.test/about#two", "# About\nSecond source.\n")])
    result = inventory_module.inventory(tmp_path)
    pages = result["pages"]
    assert len(pages) == len({p["page_id"] for p in pages}) == 2
    assert len({p["raw_sha256"] for p in pages}) == 2
    assert {p["manifest_index"] for p in pages} == {0, 1}
    assert len({p["canonical_url"] for p in pages}) == 1
    assert result["summary"]["snapshots"][0]["distinct_content_collision_groups"] == 1
    assert len(result["source_clusters"]["canonical_groups"][0]["page_ids"]) == 2


def test_manifest_reordering_changes_only_original_positions_and_manifest_hash(tmp_path):
    snapshot = make_snapshot(tmp_path, [("pages/a.md", "https://example.test/about", "# About\nA sentence."),
                                       ("pages/b.md", "https://example.test/personal/checking", "# Checking\nA different sentence.")])
    first = inventory_module.inventory(tmp_path)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["pages"].reverse()
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    second = inventory_module.inventory(tmp_path)
    assert [p["page_id"] for p in first["pages"]] == [p["page_id"] for p in second["pages"]]
    assert [p["manifest_index"] for p in first["pages"]] == list(reversed([p["manifest_index"] for p in second["pages"]]))
    for data in (first, second):
        for page in data["pages"]:
            page.pop("manifest_index")
        for snap in data["summary"]["snapshots"]:
            snap.pop("manifest_sha256")
    assert first == second


def test_identical_duplicate_manifest_records_are_not_lost(tmp_path):
    snapshot = make_snapshot(tmp_path, [("pages/a.md", "https://example.test/about", "# About\nOne source.")])
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["pages"] *= 2
    path.write_text(json.dumps(manifest))
    result = inventory_module.inventory(tmp_path)
    assert len(result["pages"]) == 2
    assert len({page["page_id"] for page in result["pages"]}) == 2
    assert len(result["source_clusters"]["identical_content_groups"][0]["page_ids"]) == 2


def test_reordered_variants_keep_their_fetch_metadata_identity(tmp_path):
    snapshot = make_snapshot(tmp_path, [("pages/a.md", "https://example.test/about", "# About\nOne source.")])
    path = snapshot / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["pages"].append({**manifest["pages"][0], "fetched_at": "2026-01-02T00:00:00Z"})
    path.write_text(json.dumps(manifest))
    first = inventory_module.inventory(tmp_path)
    manifest["pages"].reverse()
    path.write_text(json.dumps(manifest))
    second = inventory_module.inventory(tmp_path)
    identity = lambda result: {p["fetched_at"]: p["page_id"] for p in result["pages"]}
    assert identity(first) == identity(second)
    assert len(set(identity(first).values())) == 2


def test_all_source_classes_and_numbered_newsroom_pages_remain(tmp_path):
    paths = ["hubfs/terms.pdf", "about", "personal/checking", "newsroom/story", "newsroom/story-2",
             "blog/article", "business/resources/article", "newsroom", "calculators/savings", "contact"]
    make_snapshot(tmp_path, [("pages/{}.md".format(i), "https://example.test/" + path,
                              "# Source\nUndated useful evidence.") for i, path in enumerate(paths)])
    result = inventory_module.inventory(tmp_path)
    assert len(result["pages"]) == len(paths)
    assert {p["page_type"] for p in result["pages"]} >= {
        "pdf", "about", "product_page", "newsroom", "blog", "business_resource", "listing", "calculator", "contact"}
    assert all(page["disposition"] == "source_review" for page in result["pages"])


def test_block_structure_date_evidence_and_navigation_are_retained(tmp_path):
    text = ("# Account\nPublished January 2, 2025\n\n## Charges\n"
            "| Service | Fee |\n| --- | --- |\n| Transfer | $2 |\nEffective March 1, 2026\n\n"
            "## Handpicked for You\n#### First article\n[Another post](https://example.test/blog/other)\n"
            "#### Second article\nAnother article summary.\n\n"
            "## Navigation\n[Contact](https://example.test/contact)\n")
    make_snapshot(tmp_path, [("pages/a.md", "https://example.test/personal/checking", text)])
    result = inventory_module.inventory(tmp_path, include_text=True)
    blocks = result["blocks"]
    assert any(b["kind"] == "heading" and b["text"] == "# Account" for b in blocks)
    table = next(b for b in blocks if b["kind"] == "table")
    assert table["heading_path"] == ["Account", "Charges"]
    assert table["row_count"] == 1
    assert table["effective_date_cue"] == "2026-03-01"
    assert {b["disposition"] for b in blocks} >= {"related_article_review", "navigation_review", "content_review"}
    second_heading = next(b for b in blocks if b.get("text") == "#### Second article")
    assert second_heading["heading_path"] == ["Account", "Handpicked for You", "Second article"]
    assert {d["preceding_cue"] for d in result["pages"][0]["date_evidence"]} == {"published", "effective"}
    metadata_only = inventory_module.inventory(tmp_path)
    assert not any("text" in block for block in metadata_only["blocks"])


def test_missing_and_unsafe_sources_are_visible_and_quarantined(tmp_path):
    snapshot = make_snapshot(tmp_path, [])
    outside = tmp_path / "outside.md"
    outside.write_text("Private outside content.")
    manifest = {"pages": [{"file": "../outside.md", "url": "https://example.test/about"},
                          {"file": "missing.md", "url": "not-a-url"}]}
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    result = inventory_module.inventory(tmp_path, include_text=True)
    assert result["summary"]["quarantined_pages"] == 2
    assert len(result["pages"]) == 2
    assert not result["blocks"]
    assert all(p["errors"] for p in result["pages"])


def test_dates_keep_unqualified_or_invalid_evidence_without_applicability_inference():
    evidence = inventory_module.date_evidence(["January 5, 2024", "Effective 2026-02-30", "Offer until 12/31/2026"])
    assert evidence[0]["preceding_cue"] is None
    assert evidence[1]["parsed_date"] is None
    assert evidence[2]["preceding_cue"] == "until"


def test_detailed_output_cannot_be_written_to_tracked_checkout_directory(tmp_path):
    with pytest.raises(ValueError, match="ignored results/phase4"):
        inventory_module.write_inventory({}, inventory_module.ROOT / "docs" / "private-inventory")
    with pytest.raises(ValueError, match="no snapshot manifests"):
        inventory_module.inventory(tmp_path)
