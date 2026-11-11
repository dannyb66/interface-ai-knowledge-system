#!/usr/bin/env python3
"""Census of table-row labels across the snapshots, used once to seed the product registry and then to check it.

Usage: python scripts/build_registry.py --snapshots snapshots --out /tmp/census.json [--check]

Walks every table row of every page of every snapshot (``0*_*`` under ``--snapshots``) through
kb.blocks.split_blocks and kb.blocks.table_rows, exactly as tests/test_15_registry.py does, and prints and
writes every distinct (canonical_url, heading, row_label) triple with its row count and the snapshot ids it
occurs in, plus the page type, segment, column kinds and one raw row. ``heading`` is the block's heading path
joined with `` > ``. Rows with an empty label (``Term | APR`` tables, whose product is the section heading)
are listed too, because the extractor resolves them by section. When submission/data/products.json exists
each triple also carries its resolution (product id and qualifiers, ``ignored`` or ``unmapped``) and the
unmapped triples are listed last; ``--check`` exits 1 when any remain. The census seeded ``label_rules``
once; products.json is hand-edited from then on. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.blocks import load_boilerplate, split_blocks, table_rows  # noqa: E402
from kb.config import DEFAULT_DATA_DIR  # noqa: E402
from kb.normalize import canonical_url  # noqa: E402
from kb.pagetype import classify, segment_of  # noqa: E402
from kb.registry import Registry  # noqa: E402

Key = Tuple[str, Tuple[str, ...], str]


def census(snapshots_dir: Path) -> List[Dict[str, Any]]:
    """One entry per distinct (canonical_url, heading_path, row_label), sorted by URL, heading and label."""
    found: Dict[Key, Dict[str, Any]] = {}
    boilerplate = load_boilerplate()
    for snap in sorted(snapshots_dir.glob("0*_*")):
        manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            md = (snap / page["file"]).read_text(encoding="utf-8")
            cu = canonical_url(page["url"])
            for block in split_blocks(md, boilerplate):
                if block.kind != "table":
                    continue
                for row in table_rows(block):
                    key = (cu, block.heading_path, row.label)
                    entry = found.get(key)
                    if entry is None:
                        entry = found[key] = {
                            "canonical_url": cu, "heading": " > ".join(block.heading_path),
                            "heading_path": list(block.heading_path), "row_label": row.label, "count": 0,
                            "snapshots": [], "page_type": classify(page["url"], md),
                            "segment": segment_of(cu, block.heading_path), "columns": [], "example": row.raw,
                        }
                    entry["count"] += 1
                    if snap.name not in entry["snapshots"]:
                        entry["snapshots"].append(snap.name)
                    if list(row.columns) not in entry["columns"]:
                        entry["columns"].append(list(row.columns))
    return [found[k] for k in sorted(found)]


def annotate(entries: List[Dict[str, Any]], registry: Registry) -> None:
    """Add ``resolution`` (a product id, ``ignored`` or ``unmapped``) and ``qualifiers`` to every entry."""
    for e in entries:
        res = registry.resolve(e["canonical_url"], tuple(e["heading_path"]), e["row_label"], e["segment"])
        e["resolution"] = "unmapped" if res is None else ("ignored" if res.ignored else res.product_id)
        e["qualifiers"] = {} if res is None else res.qualifiers


def _line(e: Dict[str, Any]) -> str:
    snaps = ",".join(s[:2] for s in e["snapshots"])
    tail = ""
    if "resolution" in e:
        tail = "  -> {} {}".format(e["resolution"], json.dumps(e["qualifiers"], sort_keys=True) if e["qualifiers"] else "")
    return "{:5d}  {:14s}  {} | {} | {!r}{}".format(e["count"], snaps, e["canonical_url"], e["heading"],
                                                  e["row_label"], tail.rstrip())


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Census of table-row labels for the product registry.")
    ap.add_argument("--snapshots", type=Path, default=ROOT / "snapshots", help="directory holding 0*_* snapshots")
    ap.add_argument("--out", type=Path, required=True, help="where to write the census JSON")
    ap.add_argument("--registry", type=Path, default=DEFAULT_DATA_DIR / "products.json")
    ap.add_argument("--check", action="store_true", help="exit 1 when any triple is unmapped")
    args = ap.parse_args(argv)
    if not any(args.snapshots.glob("0*_*/manifest.json")):
        ap.error("no 0*_*/manifest.json under {}".format(args.snapshots))
    entries = census(args.snapshots)
    registry = Registry.load(args.registry) if args.registry.is_file() else None
    if registry is not None:
        annotate(entries, registry)
    for e in entries:
        print(_line(e))
    rows = sum(e["count"] for e in entries)
    print("{} distinct triples, {} rows, {} with an empty label".format(
        len(entries), rows, sum(1 for e in entries if not e["row_label"])))
    unmapped: List[Dict[str, Any]] = []
    if registry is not None:
        unmapped = [e for e in entries if e["resolution"] == "unmapped"]
        ignored = sum(1 for e in entries if e["resolution"] == "ignored")
        print("registry {}: {} triples map to products, {} ignored, {} unmapped".format(
            registry.version, len(entries) - ignored - len(unmapped), ignored, len(unmapped)))
        for e in unmapped:
            print("UNMAPPED " + _line(e))
    else:
        print("no registry at {}; resolutions skipped".format(args.registry))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote {}".format(args.out))
    return 1 if args.check and (registry is None or unmapped) else 0


if __name__ == "__main__":
    sys.exit(main())
