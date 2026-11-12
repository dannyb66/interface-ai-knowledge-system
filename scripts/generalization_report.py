#!/usr/bin/env python3
"""Report source-first semantic outcomes; never expose blind per-question misses."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
from statistics import mean

from generalization_audit import validate_judgment
from generalization_common import (FLOOR, MIN_CLUSTERS, VERSION, file_hash, indexed,
                                   load_gold, rows, write_json)


def interval(families, seed=0, draws=2000):
    """Stratified cluster bootstrap; wordings never increase independent n."""
    if not families:
        return None
    rng, samples = random.Random(seed), []
    for _ in range(draws):
        samples.append(mean(mean(rng.choices(values, k=len(values))) for values in families.values()))
    samples.sort()
    return {"low": samples[int(0.025 * draws)], "high": samples[min(draws - 1, int(0.975 * draws))],
            "method": "stratified cluster bootstrap percentile", "draws": draws,
            "seed": seed, "warning": "Small or constant samples can yield narrow intervals; not universal guarantees."}


def summarize(gold, results, audits, manifest, dataset_hash, rubric_hash):
    result_map, audit_map = indexed(results), indexed(audits)
    if set(result_map) != set(gold) or set(audit_map) != set(gold):
        raise ValueError("results/audits must exactly cover frozen question IDs")
    by_scenario, outcomes = defaultdict(list), {}
    totals = dict(questions=len(gold), passed_questions=0, answerable_questions=0, answered_answerable=0,
                  refused_questions=0, appropriate_refusals=0, unsupported_confident_claims=0,
                  known_stale_claims=0, errors=0, official_trap_hits=0, accepted_citation_failures=0,
                  accepted_temporal_failures=0)
    scores, weights = [], []
    for key, item in gold.items():
        result, audit = result_map[key], audit_map[key]
        passed = validate_judgment(item, result, audit, dataset_hash, rubric_hash)
        outcomes[key] = passed
        by_scenario[item["scenario_id"]].append(key)
        confident = result["answer"]["confident"]
        refused = audit["observed_verdict"] == "refuse"
        totals["passed_questions"] += passed
        totals["answerable_questions"] += item["answerable"]
        totals["answered_answerable"] += bool(item["answerable"] and confident and not refused)
        totals["refused_questions"] += refused
        totals["appropriate_refusals"] += bool(not item["answerable"] and refused and passed)
        totals["unsupported_confident_claims"] += (max(audit["unsupported_claims"], int(not audit["supported"]))
                                                   if confident else 0)
        totals["known_stale_claims"] += audit["known_stale_claims"]
        totals["errors"] += bool(result.get("error"))
        totals["official_trap_hits"] += bool(result.get("trap_hits"))
        totals["accepted_citation_failures"] += bool(confident and (not audit["citation_supported"] or
                                                                   not result["answer"]["sources"]))
        totals["accepted_temporal_failures"] += bool(confident and not audit["temporally_valid"])
        weight, score = result.get("weight", 1), result.get("score")
        if (type(weight) not in (int, float) or type(score) not in (int, float)
                or not math.isfinite(weight) or not math.isfinite(score) or weight <= 0 or not 0 <= score <= 1
                or weight != item["question"].get("weight", 1)):
            raise ValueError("invalid official score/weight")
        weights.append(weight)
        scores.append(weight * score)
    cluster_values, family_scenarios = defaultdict(list), defaultdict(list)
    for keys in by_scenario.values():
        item = gold[keys[0]]
        verdicts = {audit_map[key]["observed_verdict"] for key in keys}
        passed = (all(outcomes[key] for key in keys) and len(verdicts) == 1
                  and all(audit_map[key]["paraphrase_consistent"] for key in keys))
        cluster_values[(item["family"], item["cluster_id"])].append(int(passed))
        family_scenarios[item["family"]].append(int(passed))
    family_clusters = defaultdict(dict)
    for (family, cluster), values in cluster_values.items():
        family_clusters[family][cluster] = mean(values)
    family_names = (manifest["family_counts"] if "family_counts" in manifest else
                    manifest["counts"]["family_clusters"])
    table, eligible = {}, {}
    for family in sorted(family_names):
        values, scenarios = list(family_clusters[family].values()), family_scenarios[family]
        n = len(values)
        table[family] = {"independent_clusters": n, "scenarios": len(scenarios),
                         "passed_scenarios": sum(scenarios), "semantic_success": mean(values) if values else None,
                         "minimum_for_numeric_gate": MIN_CLUSTERS,
                         "status": "standard_n" if n >= MIN_CLUSTERS else "small_n" if n else "unvalidated",
                         "all_reserved_pass": bool(scenarios) and all(scenarios),
                         "cluster_interval": interval({family: values}) if values else None}
        if n >= MIN_CLUSTERS:
            eligible[family] = values
    totals["answerable_coverage"] = (totals["answered_answerable"] / totals["answerable_questions"]
                                     if totals["answerable_questions"] else None)
    totals["refusal_precision"] = (totals["appropriate_refusals"] / totals["refused_questions"]
                                   if totals["refused_questions"] else None)
    return {"version": VERSION, "dataset_sha256": dataset_hash, "rubrics_sha256": rubric_hash,
            "official_qa": sum(scores) / sum(weights), "semantic_questions": totals,
            "families": table, "primary_families": sorted(eligible),
            "primary_macro": mean(mean(v) for v in eligible.values()) if eligible else None,
            "primary_interval": interval(eligible),
            "all_sampled_macro": mean(mean(v.values()) for v in family_clusters.values()) if cluster_values else None,
            "independent_clusters": len(cluster_values), "scenarios": len(by_scenario),
            "_clusters": dict(family_clusters)}


def paired(candidate, baseline):
    if ((candidate["dataset_sha256"], candidate["rubrics_sha256"]) !=
            (baseline["dataset_sha256"], baseline["rubrics_sha256"])):
        raise ValueError("paired runs must use identical frozen truth")
    if candidate["primary_families"] != baseline["primary_families"]:
        raise ValueError("paired runs have different independent family populations")
    differences, family_deltas = {}, {}
    for family, values in candidate["_clusters"].items():
        old = baseline["_clusters"].get(family, {})
        if set(values) != set(old):
            raise ValueError("paired claim clusters do not match")
        delta = [values[key] - old[key] for key in sorted(values)]
        family_deltas[family] = mean(delta)
        if family in candidate["primary_families"]:
            differences[family] = delta
    return {"primary_delta": mean(mean(v) for v in differences.values()) if differences else None,
            "primary_delta_interval": interval(differences), "family_deltas": family_deltas,
            "interpretation": "Paired observed improvement; broad uncertainty is not proof of universal generalization."}


def gate_failures(summary, comparison=None):
    failures = []
    if summary["primary_macro"] is None or summary["primary_macro"] < FLOOR:
        failures.append("primary semantic macro below floor or unavailable")
    for name, stats in summary["families"].items():
        if stats["status"] == "small_n" and not stats["all_reserved_pass"]:
            failures.append("sparse family did not pass every reserved scenario: " + name)
        if stats["status"] == "standard_n" and ("description" in name or "eligibility" in name):
            if stats["semantic_success"] < FLOOR:
                failures.append("required family semantic floor: " + name)
    for name in ("unsupported_confident_claims", "known_stale_claims", "errors", "accepted_temporal_failures",
                 "accepted_citation_failures"):
        if summary["semantic_questions"][name]:
            failures.append(name)
    if comparison is None:
        failures.append("frozen paired comparison missing")
    else:
        if comparison["primary_delta"] is None or comparison["primary_delta"] <= 0:
            failures.append("positive paired primary improvement not established")
        if any(value < -1e-12 for value in comparison["family_deltas"].values()):
            failures.append("sampled family regression")
    return failures


def public_summary(summary):
    return {key: value for key, value in summary.items() if not key.startswith("_")}


def verify_campaign(root, questions, rubrics, manifest, candidate_results, baseline_results):
    from generalization_ledger import read_campaign, tools_hashes
    campaign, events, _ = read_campaign(root.resolve())
    if tools_hashes() != campaign["tool_sha256"]:
        raise ValueError("frozen comparison tooling changed")
    for name, path in (("questions", questions), ("rubrics", rubrics), ("freeze", manifest)):
        if file_hash(path) != campaign["inputs"][name]["sha256"]:
            raise ValueError("report inputs differ from the registered comparison")
    for role, path in (("candidate", candidate_results), ("baseline", baseline_results)):
        completed = [e for e in events if e["action"] == "finished" and e.get("role") == role]
        if (len(completed) != 1 or completed[0]["returncode"] != 0 or completed[0].get("failure")
                or path is None or completed[0]["output_sha256"].get("per_question.jsonl") != file_hash(path)):
            raise ValueError("report is not using both successful registered runtime outputs")
    return campaign["commits"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("questions", "rubrics", "manifest", "results", "audit"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--baseline-results", type=Path)
    parser.add_argument("--baseline-audit", type=Path)
    parser.add_argument("--out", type=Path, help="aggregate JSON only; safe for publication after review")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--campaign", type=Path, help="required for a blind release gate")
    args = parser.parse_args(argv)
    try:
        gold, manifest = load_gold(args.questions, args.rubrics, args.manifest)
        dh, rh = file_hash(args.questions), file_hash(args.rubrics)
        summary = summarize(gold, rows(args.results), rows(args.audit), manifest, dh, rh)
        comparison = None
        if bool(args.baseline_results) != bool(args.baseline_audit):
            raise ValueError("baseline results and audit must be supplied together")
        if args.baseline_results:
            baseline = summarize(gold, rows(args.baseline_results), rows(args.baseline_audit), manifest, dh, rh)
            comparison = paired(summary, baseline)
            summary["paired"] = comparison
            summary["baseline"] = public_summary(baseline)
        if args.gate and manifest["schema_version"] == "phase4-source-blind-freeze-v1":
            if args.campaign is None:
                raise ValueError("blind release gate requires the registered campaign")
            summary["comparison_commits"] = verify_campaign(args.campaign, args.questions, args.rubrics,
                                                            args.manifest, args.results, args.baseline_results)
        failures = gate_failures(summary, comparison) if args.gate else []
        output = public_summary(summary)
        output["gate"] = {"requested": args.gate, "passed": not failures if args.gate else None, "failures": failures}
        if args.out:
            write_json(args.out, output, private=False)
        print(json.dumps(output, sort_keys=True, allow_nan=False))
        return int(bool(failures))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error("incomplete or invalid semantic comparison: " + str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
