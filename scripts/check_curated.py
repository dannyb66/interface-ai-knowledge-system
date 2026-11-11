"""Check the curated conflicts list on the crawls: every entry must verify.

    python scripts/check_curated.py

Loads ``CURATED`` (``submission/data/conflicts_curated.json``; a file that does not parse is reported and fails the
check), then ingests every crawl under ``snapshots/`` through the facade built on that file's folder
(``solution.build(data_dir=CURATED.parent)``, so the count and the system read the same file; ``ingest`` per crawl,
with ingestion's own lines sent to stderr), exactly as the graded path verifies the entries. Prints
``curated: <v>/<n> verified`` and, for each entry that did not verify, its topic and why. Exits 1 unless every entry
verified. Offline only: nothing in ``submission/`` imports this file.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    sys.path.insert(0, str(ROOT / _folder))

import solution  # noqa: E402
from kb.conflicts import load_curated  # noqa: E402
from run_eval import load_snapshots  # noqa: E402

CURATED = ROOT / "submission" / "data" / "conflicts_curated.json"


def main(argv: Optional[List[str]] = None) -> int:
    if argv:
        print("usage: python scripts/check_curated.py", file=sys.stderr)
        return 2
    try:
        entries = load_curated(CURATED)
    except (OSError, ValueError) as exc:
        print("curated: {} does not load: {}".format(CURATED, exc))
        return 1
    ks = solution.build(data_dir=CURATED.parent)
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    emitted = {c.topic for c in ks.conflicts()}
    print("curated: {}/{} verified".format(len(emitted), len(entries)))
    why = dict(ks._book.dropped(ks.ingested))  # every entry whose crawls were all ingested and that failed
    for entry in entries:
        if entry.topic not in emitted:
            named = sorted({s.snapshot_id for s in entry.sources} - set(ks.ingested))
            print("dropped: {}: {}".format(entry.topic, why.get(entry.topic) or "crawl {} was not ingested".format(
                ", ".join(named))))
    return 0 if len(emitted) == len(entries) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
