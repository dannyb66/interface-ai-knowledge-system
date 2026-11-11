#!/usr/bin/env python3
"""The prose routing rate: the share of prose-family proxy items whose parsed (intent, product_id, attribute) equals
the triple their template intended (the item's ``route``). Plan A schedules the routing index (T3) when any prose
family with at least four items falls below 0.80; --gate enforces the phase floor of 0.90 for those families.

    python scripts/proxy_routing.py [--set PATH] [--misses] [--gate]

Prints ``prose routing rate: <x> (<n>/<m>)`` over the items of ``PROSE_FAMILIES``, then ``  <family>: <x> (<n>/<m>)``
for each prose family (``n/a (0/0)`` when it has no items) and then each other family of the set, alphabetically;
``--misses`` adds one line per misrouted item. Items without a ``route`` (the seeds) are not counted. Each question goes
through ``KnowledgeSystem._parse``, the graded path's parse (cut to ``max_question_chars``, the newest crawl's day as
``reference_date``), after the crawls under snapshots/ are ingested (their output goes to stderr). Deterministic.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

PROSE_FAMILIES = ("hours_branch", "hours_day", "hours_unlisted", "closure", "count", "count_year",
                  "description", "eligibility", "recognition", "fee")


def rate(hits: int, total: int) -> str:
    return "%.4f" % (hits / total) if total else "n/a"


def build_system():
    """``solution.build()`` with every crawl under snapshots/ ingested; ingestion's stdout goes to stderr."""
    import solution
    from run_eval import load_snapshots

    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    return ks


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="The prose routing rate of a proxy set (see the module docstring).")
    ap.add_argument("--set", type=Path, default=ROOT / "eval" / "proxy" / "proxy.jsonl", help="a set built by "
                    "scripts/build_proxy_set.py (default eval/proxy/proxy.jsonl)")
    ap.add_argument("--misses", action="store_true", help="also print each misrouted item")
    ap.add_argument("--gate", action="store_true", help="fail if any prose family with at least four items is below 0.90")
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in args.set.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.misses and any(str(row.get("id", "")).startswith("h-") for row in rows):
        ap.error("--misses cannot display holdout items")
    ks = build_system()
    tally: Dict[str, List[int]] = {}
    misses: List[str] = []
    for row in rows:
        if not row.get("route"):
            continue
        q = ks._parse(row["question"], row.get("as_of"))
        parsed = [q.intent, q.product_id, q.attribute]
        hit = parsed == list(row["route"])
        counts = tally.setdefault(row["family"], [0, 0])
        counts[0] += int(hit)
        counts[1] += 1
        if args.misses and not hit:
            misses.append("  miss %s %s: wanted %s, parsed %s | %s" % (row["family"], row["id"], row["route"], parsed,
                                                                        row["question"]))
    prose = [tally.get(family, [0, 0]) for family in PROSE_FAMILIES]
    hits, total = sum(h for h, _ in prose), sum(t for _, t in prose)
    print("prose routing rate: %s (%d/%d)" % (rate(hits, total), hits, total))
    for family in list(PROSE_FAMILIES) + sorted(f for f in tally if f not in PROSE_FAMILIES):
        h, t = tally.get(family, [0, 0])
        print("  %s: %s (%d/%d)" % (family, rate(h, t), h, t))
    eligible = [(family, tally[family]) for family in PROSE_FAMILIES if tally.get(family, [0, 0])[1] >= 4]
    minimum = min((h / t for _, (h, t) in eligible), default=None)
    print("minimum prose family routing: %s; routing-index trigger: %s" % (
        "n/a" if minimum is None else "%.4f" % minimum, "yes" if minimum is not None and minimum < 0.80 else "no"))
    if args.misses:
        print("\n".join(misses) if misses else "  (no misrouted item)")
    return int(args.gate and any(h / t < 0.90 for _, (h, t) in eligible))


if __name__ == "__main__":
    sys.exit(main())
