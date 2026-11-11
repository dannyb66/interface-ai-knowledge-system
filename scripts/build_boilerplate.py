#!/usr/bin/env python3
"""Freeze the boilerplate line list from one snapshot.

Usage: python scripts/build_boilerplate.py --snapshot 05_2026-09-28_latest --threshold 0.15

Writes submission/data/boilerplate.json as {"_version": "<ISO date> build_boilerplate v1", "lines": [...]}:
every stripped line present on at least ``threshold`` of the snapshot's pages, plus the About Dupaco
tail marker that kb.blocks.split_blocks keys on. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.blocks import ABOUT_MARKER  # noqa: E402

VERSION = "build_boilerplate v1"


def frequent_lines(snapshot_dir: Path, threshold: float) -> List[str]:
    """Stripped non-empty lines found on at least ``threshold`` of the manifest's pages, sorted."""
    pages = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))["pages"]
    pages_with: Counter = Counter()
    for page in pages:
        text = (snapshot_dir / page["file"]).read_text(encoding="utf-8")
        pages_with.update({line.strip() for line in text.split("\n") if line.strip()})
    return sorted(line for line, count in pages_with.items() if count >= threshold * len(pages))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Freeze the boilerplate line list from one snapshot.")
    ap.add_argument("--snapshot", required=True, help="snapshot id under snapshots/, e.g. 05_2026-09-28_latest")
    ap.add_argument("--threshold", type=float, default=0.15, help="share of pages a line must appear on (0-1]")
    ap.add_argument("--snapshots-dir", type=Path, default=ROOT / "snapshots")
    ap.add_argument("--out", type=Path, default=ROOT / "submission" / "data" / "boilerplate.json")
    args = ap.parse_args(argv)
    if not 0 < args.threshold <= 1:
        ap.error("--threshold must be in (0, 1], got {}".format(args.threshold))
    snapshot_dir = args.snapshots_dir / args.snapshot
    if not (snapshot_dir / "manifest.json").is_file():
        ap.error("no manifest.json under {}".format(snapshot_dir))
    lines = sorted(set(frequent_lines(snapshot_dir, args.threshold)) | {ABOUT_MARKER})
    payload = {"_version": "{} {}".format(date.today().isoformat(), VERSION), "lines": lines}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote {} lines from {} to {}".format(len(lines), args.snapshot, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
