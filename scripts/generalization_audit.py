#!/usr/bin/env python3
"""Prepare blinded source review and collect hash-bound independent judgments.

This tool checks provenance and judgment completeness; it is not an entailment
model. Source-grounded reviewers decide all semantic dimensions explicitly.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import secrets
from typing import Dict, List

from generalization_common import (DIMENSIONS, QUESTION_DIMENSIONS, VERSION, binding, check_sources, digest, file_hash,
                                   indexed, load_gold, rows, write_json, write_rows)


def validate_judgment(item: dict, result: dict, audit: dict, dataset_hash: str, rubric_hash: str) -> bool:
    """Return strict pass, raising when a review is absent, disputed or stale."""
    if (audit.get("id") != item["id"] or audit.get("binding_sha256") != binding(item, result)
            or audit.get("dataset_sha256") != dataset_hash or audit.get("rubrics_sha256") != rubric_hash):
        raise ValueError("audit is not bound to these exact data and answers")
    if (audit.get("status") not in ("reviewed", "adjudicated") or audit.get("independent") is not True
            or not isinstance(audit.get("reviewer"), str) or not audit["reviewer"].strip()
            or not isinstance(audit.get("notes"), str) or not audit["notes"].strip()):
        raise ValueError("complete independent review is required")
    if audit.get("disagreement") is not False:
        raise ValueError("reviewer disagreement must be adjudicated before scoring")
    if audit["status"] == "adjudicated" and (not isinstance(audit.get("adjudicator"), str)
                                            or not audit["adjudicator"].strip()):
        raise ValueError("adjudication provenance is required")
    if any(type(audit.get(name)) is not bool for name in DIMENSIONS):
        raise ValueError("all semantic dimensions require explicit boolean judgments")
    for name in ("unsupported_claims", "known_stale_claims"):
        if type(audit.get(name)) is not int or audit[name] < 0:
            raise ValueError("claim counts must be nonnegative integers")
    if audit.get("observed_verdict") not in ("answer", "qualified_answer", "refuse"):
        raise ValueError("reviewed verdict is required")
    answer = result.get("answer")
    if (not isinstance(answer, dict) or type(answer.get("confident")) is not bool
            or not isinstance(answer.get("text"), str) or not isinstance(answer.get("sources"), list)
            or answer.get("conflict_note") is not None and not isinstance(answer["conflict_note"], str)):
        raise ValueError("invalid organizer Answer record")
    for source in answer["sources"]:
        if (not isinstance(source, dict) or not isinstance(source.get("url"), str) or not source["url"].strip()
                or any(source.get(name) is not None and not isinstance(source[name], str)
                       for name in ("snapshot_id", "quote"))):
            raise ValueError("invalid organizer Source record")
    if audit["observed_verdict"] == "refuse" and answer["confident"]:
        # An affirmative confidence flag plus refusal prose is a calibration failure.
        return False
    if not item["answerable"]:
        verdict_ok = audit["observed_verdict"] == "refuse" and not answer["confident"]
    else:
        verdict_ok = (audit["observed_verdict"] == item["expected_verdict"]
                      and answer["confident"] is item["confident_expected"])
    return bool(verdict_ok and answer["text"].strip() and (not item["answerable"] or answer["sources"])
                and all(audit[name] for name in QUESTION_DIMENSIONS)
                and not audit["unsupported_claims"] and not audit["known_stale_claims"]
                and not result.get("error"))


def prepare(gold: Dict[str, dict], runs: Dict[str, List[dict]], dataset_hash: str,
            rubric_hash: str, seed=None) -> tuple:
    """Randomize run identity/order, retaining private custodian bindings separately."""
    if not 1 <= len(runs) <= 2:
        raise ValueError("prepare one development run or one paired comparison")
    indexed_runs = {name: indexed(values) for name, values in runs.items()}
    if any(set(values) != set(gold) for values in indexed_runs.values()):
        raise ValueError("result IDs must exactly match source gold")
    failures = sum(bool(check_sources(item)) for item in gold.values())
    if failures:
        raise ValueError("source evidence verification failed; no review pack created")
    rng = random.Random(secrets.randbits(128) if seed is None else seed)
    groups, mapping, pack = {}, {}, []
    for name, results in sorted(indexed_runs.items()):
        for key, item in sorted(gold.items()):
            opaque = "review-{:032x}".format(rng.getrandbits(128))
            group = groups.setdefault((name, item["scenario_id"]), "group-{:032x}".format(rng.getrandbits(128)))
            result = results[key]
            sha = binding(item, result)
            mapping[opaque] = {"run": name, "id": key, "binding_sha256": sha,
                               "dataset_sha256": dataset_hash, "rubrics_sha256": rubric_hash}
            rubric = {field: item[field] for field in ("answerable", "expected_verdict", "confident_expected",
                       "required_claims", "required_conditions", "forbidden_claims", "evidence")}
            rubric["guidance"] = {field: item["raw_rubric"][field] for field in
                                  ("required_verdict", "unknown_details", "optional_context_claims", "semantic_scoring",
                                   "expected_behavior", "source_dates", "evaluation_contract") if field in item["raw_rubric"]}
            record = {"review_id": opaque, "paraphrase_group": group,
                         "question": item["question"]["question"], "as_of": item["question"].get("as_of"),
                         "rubric": rubric, "answer": result["answer"], "runtime_error": bool(result.get("error")),
                         "judgment": {"status": "unreviewed", "reviewer": None, "independent": None,
                                      "disagreement": None, "adjudicator": None,
                                      **{field: None for field in DIMENSIONS}, "observed_verdict": None,
                                      "unsupported_claims": None, "known_stale_claims": None, "notes": None}}
            mapping[opaque]["review_content_sha256"] = digest({k: v for k, v in record.items() if k != "judgment"})
            pack.append(record)
    rng.shuffle(pack)
    return ({"version": VERSION, "dataset_sha256": dataset_hash, "rubrics_sha256": rubric_hash,
             "records": mapping, "run_names": sorted(runs)}, pack)


def collect(mapping: dict, reviewed: List[dict]) -> Dict[str, List[dict]]:
    records = indexed(reviewed, "review_id")
    if set(records) != set(mapping["records"]):
        raise ValueError("review pack coverage is incomplete or duplicated")
    output = defaultdict(list)
    for key, link in mapping["records"].items():
        review = records[key]
        judgment = review.get("judgment")
        if digest({k: v for k, v in review.items() if k != "judgment"}) != link["review_content_sha256"]:
            raise ValueError("review pack question, evidence or answer was altered")
        if not isinstance(judgment, dict):
            raise ValueError("judgment object is required")
        # Caller-supplied IDs/hashes may never replace the custodian binding.
        if set(judgment) & {"id", "binding_sha256", "dataset_sha256", "rubrics_sha256", "run"}:
            raise ValueError("judgment must not supply custodian identity fields")
        output[link["run"]].append({**judgment, **{k: v for k, v in link.items() if k not in ("run", "review_content_sha256")}})
    return {name: sorted(values, key=lambda row: row["id"]) for name, values in output.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("questions", "rubrics", "manifest", "out"):
        prep.add_argument("--" + name, type=Path, required=True)
    prep.add_argument("--results", type=Path, required=True, help="first per_question.jsonl")
    prep.add_argument("--paired-results", type=Path, help="second per_question.jsonl")
    col = sub.add_parser("collect")
    for name in ("mapping", "reviewed", "out"):
        col.add_argument("--" + name, type=Path, required=True)
    chk = sub.add_parser("check-sources")
    for name in ("questions", "rubrics", "manifest"):
        chk.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
            outputs = collect(mapping, rows(args.reviewed))
            for name, values in outputs.items():
                if name not in ("run_a", "run_b"):
                    raise ValueError("unsupported run label in mapping")
                write_rows(args.out / (name + ".audit.jsonl"), values)
            print(json.dumps({"collected_runs": len(outputs), "judgments": sum(map(len, outputs.values()))}))
        else:
            gold, _ = load_gold(args.questions, args.rubrics, args.manifest)
            if args.command == "check-sources":
                bad = sum(bool(check_sources(item)) for item in gold.values())
                print(json.dumps({"questions": len(gold), "source_failures": bad,
                                  "semantic_review_required": True}))
                return int(bool(bad))
            runs = {"run_a": rows(args.results)}
            if args.paired_results:
                runs["run_b"] = rows(args.paired_results)
            mapping, pack = prepare(gold, runs, file_hash(args.questions), file_hash(args.rubrics))
            mapping["result_files_sha256"] = {"run_a": file_hash(args.results)}
            if args.paired_results:
                mapping["result_files_sha256"]["run_b"] = file_hash(args.paired_results)
            write_json(args.out / "custodian-mapping.json", mapping)
            write_rows(args.out / "review-pack.jsonl", pack)
            print(json.dumps({"review_records": len(pack), "runs": len(runs), "semantic_review_required": True}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error("audit preparation/validation failed: " + str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
