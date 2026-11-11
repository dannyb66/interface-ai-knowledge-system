"""Print a deterministic random sample of a snapshot's pages as url<TAB>file.

Picks the pages behind the locked question set (eval/locked/). Before sampling it drops
HubSpot modal/tracking URLs (campaignId, hsLang), PDF-derived pages, and newsroom slug
duplicates: HubSpot re-uses a title's slug with a -2/-3 counter (one board-election
release per year), so a /newsroom/ path that equals an earlier one once a trailing -<digits>
is removed is skipped (first seen in manifest order wins).

    python scripts/sample_pages.py --snapshot 05_2026-09-28_latest --n 30 --seed 20261104
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

COUNTER_RE = re.compile(r"-\d+$")


def eligible(pages: list[dict]) -> list[dict]:
    """Manifest pages that may be sampled, in manifest order."""
    keep, seen = [], set()
    for page in pages:
        url, file = page["url"].lower(), page["file"].lower()
        if "campaignid" in url or "hslang" in url:
            continue
        if url.endswith((".pdf", ".pdf.md")) or file.endswith((".pdf", ".pdf.md")):
            continue
        path = urlparse(url).path.rstrip("/")
        if "/newsroom/" in path:
            slug = COUNTER_RE.sub("", path)
            if slug in seen:
                continue
            seen.add(slug)
        keep.append(page)
    return keep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", required=True, help="snapshot id, e.g. 05_2026-09-28_latest")
    ap.add_argument("--n", type=int, default=30, help="pages to sample (default 30)")
    ap.add_argument("--seed", type=int, required=True, help="random.Random seed")
    ap.add_argument("--snapshots-dir", type=Path, default=Path(__file__).resolve().parents[1] / "snapshots")
    args = ap.parse_args(argv)

    manifest_path = args.snapshots_dir / args.snapshot / "manifest.json"
    if not manifest_path.is_file():
        ap.error(f"no manifest at {manifest_path}")
    pool = eligible(json.loads(manifest_path.read_text())["pages"])
    if not 0 < args.n <= len(pool):
        ap.error(f"--n must be between 1 and {len(pool)} (eligible pages)")

    for page in random.Random(args.seed).sample(pool, args.n):
        print(f"{page['url']}\t{page['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
