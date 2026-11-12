#!/usr/bin/env python3
"""Explain a frozen DEVELOPMENT set; traces are evidence, never independent gold.

--manifest declares partition=development and questions_sha256 (and
rubrics_sha256 when --rubrics is supplied), or the frozen source curator's
phase4-dev-source-gold-v1 schema with artifact_sha256 entries. Sealed paths are refused before
opening their contents. Private details stay in --out; stdout is aggregate only.
"""
from __future__ import annotations

import argparse
import contextlib
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
for folder in ("harness", "submission"):
    sys.path.insert(0, str(ROOT / folder))


def checked_input(path: Path, manifest: dict, field: str) -> bytes:
    forbidden = ("blind", "holdout", "locked", "reserved")
    if any(word in part.lower() for part in path.resolve().parts for word in forbidden):
        raise ValueError("sealed inputs cannot be diagnosed")
    source_dev = manifest.get("schema_version") == "phase4-dev-source-gold-v1"
    if manifest.get("partition") != "development" and not source_dev:
        raise ValueError("manifest must declare partition=development")
    data = path.read_bytes()
    expected = manifest.get("artifact_sha256", {}).get("dev.questions.jsonl" if field == "questions_sha256"
                   else "dev.rubrics.jsonl") if source_dev else manifest.get(field)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("development manifest hash mismatch: " + field)
    return data


def rows(data: bytes) -> list:
    items = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate development IDs")
    return items


def attribution(info: dict, rubric: Optional[dict]) -> dict:
    """Conservative hypotheses. Only a source reviewer can establish a true failure stage."""
    reasons = [row["reason"] for row in info["trace"]["refusals"]]
    stage = "unresolved"
    expected = (rubric or {}).get("expected_route", {})
    parsed = info["trace"]["parser"]
    if any(parsed.get(name, {}).get("value") != value for name, value in expected.items()
           if name in ("entity", "attribute", "intent", "as_of")):
        stage = "parsing"
    elif "rendering_grounding" in reasons:
        stage = "rendering"
    elif (rubric or {}).get("answerability") is True and not info["confident"]:
        stage = "parsing" if "unknown_entity" in reasons else "evidence_or_selection"
    elif (rubric or {}).get("answerability") is False and info["confident"]:
        stage = "refusal_or_rendering"
    return {"suspected_stage": stage, "refusal_reasons": reasons, "requires_source_review": True}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rubrics", type=Path)
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    parser.add_argument("--out", type=Path, default=ROOT / "results/phase4/diagnostics.jsonl")
    args = parser.parse_args(argv)
    try:
        if any(word in part.lower() for part in args.manifest.resolve().parts for word in ("blind", "holdout", "locked", "reserved")):
            raise ValueError("sealed manifests cannot be diagnosed")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        items = rows(checked_input(args.eval, manifest, "questions_sha256"))
        rubrics = {row["id"]: row for row in rows(checked_input(args.rubrics, manifest, "rubrics_sha256"))} if args.rubrics else {}
        if rubrics and set(rubrics) != {row["id"] for row in items}:
            raise ValueError("development rubric/question IDs differ")
        try:
            relative = args.out.resolve().relative_to(ROOT)
        except ValueError:
            relative = None
        if relative is not None and relative.parts[:2] != ("results", "phase4"):
            raise ValueError("private diagnostics must use ignored results/phase4 or an external local directory")
        import solution
        from run_eval import load_snapshots
        ks = solution.build()
        with contextlib.redirect_stdout(sys.stderr):
            for snapshot in load_snapshots(args.snapshots):
                ks.ingest(snapshot)
        records = []
        for item in items:
            info = ks.explain(item["question"], item.get("as_of"))
            records.append({"id": item["id"], "diagnosis": attribution(info, rubrics.get(item["id"])), "explain": info})
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"questions": len(records), "suspected_stages": dict(Counter(
        row["diagnosis"]["suspected_stage"] for row in records)), "independent_truth": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
