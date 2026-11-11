#!/usr/bin/env python3
"""Aggregate family scores and enforce the Phase 3 proxy gate without exposing item contents.

The generated-only weighted score excludes both seed families and zero-weight diagnostics.
Use --reference-results with a holdout run to compare against that generated-only proxy score.
--gate enforces the binding per-family thresholds, seed score, macro blend and consistency.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
SEEDS = frozenset(("paraphrase", "probe"))
FAMILY_FLOORS = {"rate_current": 0.98, "rate_as_of": 0.98, "rate_change": 0.95,
                 "tier_amount": 0.97, "hours_branch": 0.97, "hours_day": 0.97,
                 "refuse_unpublished": 1.0, "hours_unlisted": 1.0,
                 "description": 0.70, "eligibility": 0.70, "recognition": 0.70, "fee": 0.70}


def rows(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(items: Sequence[dict], results: Sequence[dict]) -> Dict[str, Any]:
    families = {row["id"]: row.get("family", "unlabeled") for row in items}
    if len(families) != len(items) or {row["id"] for row in results} != set(families) or len(results) != len(items):
        raise ValueError("set/result IDs are incomplete or duplicated")
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for result in results:
        buckets[families[result["id"]]].append(result)

    def score(group: Sequence[dict]) -> Optional[float]:
        weight = sum(float(row.get("weight", 1)) for row in group)
        return sum(float(row["score"]) * float(row.get("weight", 1)) for row in group) / weight if weight else None

    table = {family: {"count": len(group), "score": score(group),
                      "trap_hits": sum(bool(row.get("trap_hits")) for row in group)}
             for family, group in sorted(buckets.items())}
    generated = [row for family, group in buckets.items() if family not in SEEDS for row in group]
    seeds = [row for family, group in buckets.items() if family in SEEDS for row in group]
    rates = [stats["score"] for family, stats in table.items() if family not in SEEDS and stats["score"] is not None]
    macro = sum(rates) / len(rates) if rates else None
    seed_score = score(seeds)
    return {"families": table, "generated_score": score(generated), "seed_score": seed_score,
            "generated_macro": macro, "macro_seed_blend": (macro + seed_score) / 2
            if macro is not None and seed_score is not None else None}


def gate_failures(summary: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
    failed = []
    for family, floor in FAMILY_FLOORS.items():
        stats = summary["families"].get(family)
        if stats is None or stats["score"] is None or stats["score"] + 1e-12 < floor:
            failed.append(family)
        if stats and family in ("refuse_unpublished", "hours_unlisted") and stats["trap_hits"]:
            failed.append(family + " traps")
    for name in ("seed_score", "macro_seed_blend"):
        value = summary[name]
        if value is None or value + 1e-12 < 0.85:
            failed.append(name)
    consistency = report.get("consistency", {}).get("paraphrase_consistency")
    if consistency is None or consistency + 1e-12 < 0.95:
        failed.append("paraphrase_consistency")
    if report.get("errors") != 0:
        failed.append("errors")
    return failed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", type=Path, default=ROOT / "eval/proxy/proxy.jsonl")
    parser.add_argument("--results", type=Path, default=ROOT / "results/proxy")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--reference-results", type=Path)
    parser.add_argument("--reference-set", type=Path, default=ROOT / "eval/proxy/proxy.jsonl")
    args = parser.parse_args(argv)
    try:
        summary = summarize(rows(args.set), rows(args.results / "per_question.jsonl"))
        report = json.loads((args.results / "report.json").read_text(encoding="utf-8"))
        reference = summarize(rows(args.reference_set), rows(args.reference_results / "per_question.jsonl")) \
            if args.reference_results else None
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("could not match the evaluation set to complete result rows")
    for family, stats in summary["families"].items():
        value = "n/a" if stats["score"] is None else "%.4f" % stats["score"]
        print("family %s count=%d qa=%s traps=%d" % (family, stats["count"], value, stats["trap_hits"]))
    for key in ("generated_score", "seed_score", "generated_macro", "macro_seed_blend"):
        if summary[key] is not None:
            print("%s=%.4f" % (key, summary[key]))
    failed = gate_failures(summary, report) if args.gate else []
    if reference is not None:
        value, baseline = summary["generated_score"], reference["generated_score"]
        if value is None or baseline is None:
            parser.error("generated-family comparison needs nonzero weighted items on both sets")
        gap = abs(value - baseline)
        print("generated_only_reference=%.4f holdout_gap=%.4f within_0.05=%s" % (baseline, gap, gap <= 0.05))
        if args.gate and gap > 0.05:
            failed.append("generated_holdout_gap")
    if args.gate:
        print("proxy gate: " + ("FAIL " + ", ".join(failed) if failed else "PASS"))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
