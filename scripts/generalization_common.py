"""Strict adapters and private I/O for source-first evaluation (no runtime imports)."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List

VERSION = "phase4-semantic-v1"
MIN_CLUSTERS = 10
FLOOR = 0.85
QUESTION_DIMENSIONS = ("supported", "complete", "temporally_valid", "citation_supported",
                       "appropriate_verdict", "confidence_appropriate")
DIMENSIONS = QUESTION_DIMENSIONS + ("paraphrase_consistent",)
BLIND_SCHEMA = "phase4-source-blind-freeze-v1"
DEV_SCHEMA = "phase4-dev-source-gold-v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> List[dict]:
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in values):
        raise ValueError("JSONL must contain objects")
    return values


def indexed(values: List[dict], field: str = "id") -> Dict[str, dict]:
    result = {}
    for row in values:
        key = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("missing or duplicate record identity")
        result[key] = row
    return result


def private_path(path: Path) -> Path:
    """Resolve symlinks; private output inside any Git checkout must be ignored."""
    path = path.resolve()
    parent = path if path.is_dir() else path.parent
    while not parent.exists():
        parent = parent.parent
    git = subprocess.run(["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if git.returncode == 0:
        root = Path(git.stdout.strip())
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--quiet", str(path)])
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", str(path)],
                                 capture_output=True)
        if ignored.returncode or tracked.returncode == 0:
            raise ValueError("private output must be outside Git or in an ignored path")
    return path


def write_json(path: Path, value: Any, private: bool = True, exclusive: bool = True) -> None:
    path = private_path(path) if private else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def write_rows(path: Path, values: List[dict]) -> None:
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for value in values:
            stream.write(canonical(value).decode("utf-8") + "\n")


def _blind(raw: dict, question: dict) -> dict:
    behavior = raw["expected_behavior"]
    answerable = raw["answerability"] in ("answerable", "answerable_qualified")
    if raw["answerability"] not in ("answerable", "answerable_qualified", "unsupported", "insufficient_information"):
        raise ValueError("unknown blind answerability")
    if (behavior["should_answer"] is not answerable or behavior["should_refuse"] is answerable
            or behavior["confident_expected"] is not answerable):
        raise ValueError("contradictory expected behavior")
    verdict = "qualified_answer" if raw["answerability"] == "answerable_qualified" else "answer" if answerable else "refuse"
    if behavior["verdict"] != verdict:
        raise ValueError("contradictory expected verdict")
    return {"scenario_id": raw["scenario_id"], "cluster_id": raw["cluster_id"], "family": raw["family"],
            "answerable": answerable, "expected_verdict": verdict, "confident_expected": answerable,
            "required_claims": raw["required_claims"], "required_conditions": raw["required_conditions"],
            "forbidden_claims": raw["forbidden_claims"], "evidence": raw["evidence"], "raw_rubric": raw}


def _dev(raw: dict, question: dict) -> dict:
    if raw["answerability"] not in ("answerable", "unanswerable"):
        raise ValueError("unknown development answerability")
    answerable = raw["answerability"] == "answerable"
    kinds = {"supported_answer": "answer", "qualified_correction": "qualified_answer", "scoped_refusal": "refuse"}
    verdict = kinds[raw["answer_kind"]]
    if (verdict == "refuse") == answerable or raw["id"] != raw["case_id"]:
        raise ValueError("contradictory development verdict/identity")
    claims = indexed(raw["claims"], "claim_id")
    if set(raw["required_claim_ids"]) - set(claims):
        raise ValueError("required claim has no meaning")
    return {"scenario_id": raw["scenario_id"], "cluster_id": raw["cluster_id"], "family": raw["family"],
            "answerable": answerable, "expected_verdict": verdict, "confident_expected": answerable,
            "required_claims": [claims[key]["meaning"] for key in raw["required_claim_ids"]],
            "required_conditions": raw["required_conditions"], "forbidden_claims": raw["forbidden_claims"],
            "evidence": raw["source_refs"], "raw_rubric": raw}


def normalize(questions: List[dict], rubrics: List[dict], manifest: dict) -> Dict[str, dict]:
    """Expand the two declared source-gold schemas; never infer an unknown schema."""
    qs, result = indexed(questions), {}
    if not qs:
        raise ValueError("evaluation dataset is empty")
    schema = manifest.get("schema_version")
    if schema == BLIND_SCHEMA:
        indexed(rubrics, "scenario_id")
        iterator = [(key, raw) for raw in rubrics for key in raw["question_ids"]]
        adapter = _blind
    elif schema == DEV_SCHEMA:
        iterator = list(indexed(rubrics).items())
        adapter = _dev
    else:
        raise ValueError("unsupported source-gold schema")
    for key, raw in iterator:
        if key not in qs or key in result:
            raise ValueError("question/rubric identities are incomplete or duplicated")
        question = qs[key]
        if raw.get("as_of") != question.get("as_of"):
            raise ValueError("question and rubric dates disagree")
        item = adapter(raw, question)
        if schema == DEV_SCHEMA and (raw["question"] != question["question"] or question["group"] != item["scenario_id"]):
            raise ValueError("development question/rubric mismatch")
        if schema == BLIND_SCHEMA:
            if (question["group"] != item["cluster_id"] or
                    question["question"] != raw["question_variants"][raw["question_ids"].index(key)]):
                raise ValueError("blind question/rubric mismatch")
        if any(not isinstance(item[name], str) or not item[name] for name in ("scenario_id", "cluster_id", "family")):
            raise ValueError("missing scenario/cluster/family")
        if not isinstance(item["evidence"], list) or not item["evidence"]:
            raise ValueError("source evidence is required")
        item.update(id=key, question=question, rubric_sha256=digest(raw))
        result[key] = item
    if set(result) != set(qs):
        raise ValueError("question/rubric coverage is incomplete")
    scenarios, clusters = defaultdict(list), {}
    for item in result.values():
        scenarios[item["scenario_id"]].append(item)
        previous = clusters.setdefault(item["cluster_id"], item["family"])
        if previous != item["family"]:
            raise ValueError("one independent cluster cannot occupy multiple families")
    for group in scenarios.values():
        if len(group) != 2 or len({x["question"]["question"].strip().casefold() for x in group}) != 2:
            raise ValueError("each scenario requires two distinct declared wordings")
        for name in ("cluster_id", "family", "answerable", "expected_verdict", "required_claims", "required_conditions", "forbidden_claims"):
            if any(x[name] != group[0][name] for x in group):
                raise ValueError("scenario wordings have inconsistent gold")
        if len({x["question"].get("as_of") for x in group}) != 1:
            raise ValueError("scenario wordings have different date scopes")
    counts = manifest.get("counts", {})
    expected_n = manifest.get("question_count", counts.get("question_wordings"))
    expected_s = manifest.get("scenario_count", counts.get("scenarios"))
    expected_c = manifest.get("independent_cluster_count", counts.get("independent_clusters"))
    if any(type(n) is not int or n < 0 for n in (expected_n, expected_s, expected_c)):
        raise ValueError("frozen census must contain integer counts")
    if (expected_n, expected_s, expected_c) != (len(qs), len(scenarios), len(clusters)):
        raise ValueError("frozen census disagrees with dataset")
    families = manifest.get("family_counts") if schema == BLIND_SCHEMA else counts.get("family_clusters")
    actual = defaultdict(set)
    for item in result.values():
        actual[item["family"]].add(item["cluster_id"])
    if not isinstance(families, dict) or set(actual) - set(families):
        raise ValueError("frozen family census missing")
    for name, stats in families.items():
        n = stats["independent_clusters"] if isinstance(stats, dict) else stats
        if type(n) is not int or n < 0 or n != len(actual[name]):
            raise ValueError("frozen family cluster count disagrees")
        if n == 0 and not (isinstance(stats, dict) and stats.get("validation_status") == "unvalidated"):
            raise ValueError("empty family requires a named frozen exception")
    return result


def load_gold(question_path: Path, rubric_path: Path, manifest_path: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = manifest.get("sha256", manifest.get("artifact_sha256", {}))
    for path in (question_path, rubric_path):
        if hashes.get(path.name) != file_hash(path):
            raise ValueError("source-gold file does not match frozen hash")
    return normalize(rows(question_path), rows(rubric_path), manifest), manifest


def binding(item: dict, result: dict) -> str:
    return digest({"question": item["question"], "rubric_sha256": item["rubric_sha256"],
                   "answer": result.get("answer"), "error": result.get("error")})


def check_sources(item: dict) -> List[str]:
    """Byte/locator checks only; this does NOT establish entailment or completeness."""
    failures = []
    for evidence in item["evidence"]:
        path = Path(evidence.get("raw_file", evidence.get("path", "")))
        try:
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != evidence["raw_sha256"]:
                raise ValueError("source hash")
            lines = body.decode("utf-8").splitlines()
            locator = evidence["locator"]
            if locator["type"] == "lines":
                start, end = locator["start"], locator["end"]
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
                    raise ValueError("source range")
                quote = evidence["quote"]
                if quote.splitlines() != lines[start - 1:end] or hashlib.sha256(quote.encode()).hexdigest() != evidence["quote_sha256"]:
                    raise ValueError("source span")
            elif locator["type"] == "one_based_line_numbers":
                numbers = locator["lines"]
                if not numbers or any(type(n) is not int or not 1 <= n <= len(lines) for n in numbers):
                    raise ValueError("source range")
                if set(evidence["limited_evidence"]) != {str(n) for n in numbers}:
                    raise ValueError("source line set")
                if any(lines[n - 1] != evidence["limited_evidence"][str(n)] for n in numbers):
                    raise ValueError("source span")
            else:
                raise ValueError("unsupported source locator")
        except (OSError, UnicodeError, KeyError, TypeError, ValueError):
            failures.append("source identity or locator check failed")
    return failures
