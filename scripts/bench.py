"""Time ``answer()`` end to end and, when ``explain()`` reports it, per stage.

    python scripts/bench.py [--n 200]

Ingests the snapshots from ``snapshots/``, then makes two passes over the first N public-eval questions in
file order. Pass 1 times one cold ``answer()`` call per question, which is what the grader's latency number
measures (minus its thread hand-off). Pass 2 calls ``explain()`` on the same questions and reads its
``timings_ms`` (``parse``, ``resolve``, ``render``); a facade whose ``explain()`` has no such key gets the
``answer`` row alone, and ``explain()`` calls that raise are counted, reported on stderr with the first error
and turn the exit status non-zero. The table is in milliseconds. Percentiles use the grader's rule from
``harness/scoring.py`` ``score_speed``: the sorted sample at index ``min(n - 1, int(q * n))``. Whatever
ingestion prints goes to stderr. The repo root comes from this file's location, so any working directory
works. Runs on Python 3.9 and newer.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    sys.path.insert(0, str(ROOT / _folder))

import solution  # noqa: E402
from run_eval import load_snapshots  # noqa: E402

STAGES = ("parse", "resolve", "render")


def percentile(samples: List[float], q: float) -> float:
    """The grader's rule (``score_speed``): the sorted sample at index ``min(n - 1, int(q * n))``."""
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def load_questions(n: int) -> List[dict]:
    lines = (ROOT / "eval" / "public_eval.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()][:n]


def time_answers(ks, items: List[dict]) -> Tuple[List[float], int]:
    """Milliseconds per ``answer()`` call, and how many calls raised (none should)."""
    samples, failures = [], 0
    for item in items:
        start = time.perf_counter()
        try:
            ks.answer(item["question"], item.get("as_of"))
        except Exception:
            failures += 1
            continue
        samples.append((time.perf_counter() - start) * 1000.0)
    return samples, failures


def time_stages(ks, items: List[dict]) -> Tuple[Dict[str, List[float]], List[str]]:
    """Milliseconds per stage from ``explain()['timings_ms']`` (the lists stay empty when it has none), and the
    ``Type: message`` text of every ``explain()`` call that raised."""
    stages = {stage: [] for stage in STAGES}
    errors = []
    for item in items:
        try:
            info = ks.explain(item["question"], item.get("as_of"))
        except Exception as exc:
            errors.append("%s: %s" % (type(exc).__name__, " ".join(str(exc).split())))
            continue
        timings = info.get("timings_ms") if isinstance(info, dict) else None
        if not isinstance(timings, dict):
            continue
        for stage in STAGES:
            value = timings.get(stage)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stages[stage].append(float(value))
    return stages, errors


def print_table(rows: List[Tuple[str, List[float]]]) -> None:
    print("%-8s %5s %10s %10s %10s" % ("stage", "n", "p50_ms", "p95_ms", "max_ms"))
    for name, samples in rows:
        print("%-8s %5d %10.3f %10.3f %10.3f" % (
            name, len(samples), percentile(samples, 0.5), percentile(samples, 0.95), max(samples)))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="p50 and p95 latency of answer() and its stages.")
    parser.add_argument("--n", type=int, default=200,
                        help="public questions to time, in file order (default 200; the set is smaller)")
    args = parser.parse_args(argv)
    if args.n < 1:
        parser.error("--n must be at least 1")

    items = load_questions(args.n)
    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        snapshots = load_snapshots(ROOT / "snapshots")
        start = time.perf_counter()
        for snapshot in snapshots:
            ks.ingest(snapshot)
        ingest_s = time.perf_counter() - start

    answers, failures = time_answers(ks, items)
    stages, explain_errors = time_stages(ks, items)
    if failures:
        print("bench: answer() raised for %d of %d questions" % (failures, len(items)), file=sys.stderr)
    if explain_errors:
        print("bench: explain() raised for %d of %d: %s" % (len(explain_errors), len(items), explain_errors[0]),
              file=sys.stderr)
    if not answers:
        return 1
    print("bench: %d public questions, %d snapshots ingested in %.2f s" % (len(items), len(snapshots), ingest_s))
    print_table([(stage, stages[stage]) for stage in STAGES if stages[stage]] + [("answer", answers)])
    if not explain_errors and not any(stages.values()):
        print("bench: explain() reports no timings_ms, so the answer row stands alone", file=sys.stderr)
    return 1 if failures or explain_errors else 0


if __name__ == "__main__":
    sys.exit(main())
