"""Independent semantics and sealed-campaign policy, using artificial source data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generalization_audit as audit
import generalization_common as common
import generalization_ledger as ledger
import generalization_report as report


def fixture_data(tmp_path, n=10, qualified=False, refuse=False):
    source = tmp_path / "source.md"
    source.write_text("# Service\nMembers pay $2 only for mailed statements.\n", encoding="utf-8")
    quote = source.read_text().splitlines()[1]
    evidence = {"snapshot_id": "test", "raw_file": str(source), "raw_url": "https://example.test/service",
                "canonical_url": "https://example.test/service", "raw_sha256": common.file_hash(source),
                "locator": {"type": "lines", "start": 2, "end": 2}, "quote": quote,
                "quote_sha256": hashlib.sha256(quote.encode()).hexdigest()}
    questions, rubrics = [], []
    verdict = "refuse" if refuse else "qualified_answer" if qualified else "answer"
    for i in range(n):
        ids = ["q{}a".format(i), "q{}b".format(i)]
        variants = ["What is the mailed-statement fee for service {}?".format(i),
                    "How much do members pay for mailed statements for service {}?".format(i)]
        raw = {"scenario_id": "s" + str(i), "cluster_id": "c" + str(i), "family": "descriptions_product_purpose",
               "question_ids": ids, "question_variants": variants, "as_of": "2026-01-01",
               "answerability": "unsupported" if refuse else "answerable_qualified" if qualified else "answerable",
               "expected_behavior": {"verdict": verdict, "should_answer": not refuse, "should_refuse": refuse,
                                     "confident_expected": not refuse},
               "required_claims": [] if refuse else ["The mailed-statement fee is $2."],
               "required_conditions": ["Members; mailed statements only."], "forbidden_claims": [], "evidence": [evidence]}
        rubrics.append(raw)
        questions.extend({"id": key, "question": text, "as_of": "2026-01-01", "group": raw["cluster_id"],
                          "category": "should_refuse" if refuse else raw["family"], "weight": 0.5,
                          "must_include": [], "must_not_include": [], "expected_sources": [evidence["raw_url"]]}
                         for key, text in zip(ids, variants))
    manifest = {"schema_version": common.BLIND_SCHEMA, "question_count": 2*n, "scenario_count": n,
                "independent_cluster_count": n,
                "family_counts": {"descriptions_product_purpose": {"independent_clusters": n}}}
    gold = common.normalize(questions, rubrics, manifest)
    results, audits = [], []
    for key, item in gold.items():
        result = {"id": key, "score": 0.15, "weight": 0.5, "error": None, "trap_hits": [],
                  "answer": {"text": "I can't confirm that." if refuse else quote,
                             "confident": not refuse, "sources": [] if refuse else [{"url": evidence["raw_url"],
                             "snapshot_id": "test", "quote": quote}], "conflict_note": None}}
        judgment = {"id": key, "binding_sha256": common.binding(item, result), "dataset_sha256": "d",
                    "rubrics_sha256": "r", "status": "reviewed", "reviewer": "independent-source-reviewer",
                    "independent": True, "disagreement": False, "notes": "Checked the exact artificial source.",
                    **{name: True for name in common.DIMENSIONS}, "observed_verdict": verdict,
                    "unsupported_claims": 0, "known_stale_claims": 0}
        results.append(result)
        audits.append(judgment)
    return questions, rubrics, manifest, gold, results, audits


def summary(data):
    _, _, manifest, gold, results, audits = data
    return report.summarize(gold, results, audits, manifest, "d", "r")


@pytest.mark.parametrize("dimension", ["supported", "complete", "appropriate_verdict", "temporally_valid", "citation_supported"])
def test_semantic_mutants_fail_even_when_official_score_is_perfect(tmp_path, dimension):
    data = fixture_data(tmp_path)
    # Independent reviewers classify wrong subject, omitted condition, false Yes,
    # stale applicability or unsupported citation. Tool enforces each judgment.
    for row in data[4]:
        row["score"] = 1
    data[5][0][dimension] = False
    result = summary(data)
    assert result["official_qa"] == 1
    assert result["families"]["descriptions_product_purpose"]["passed_scenarios"] == 9
    assert result["primary_macro"] == 0.9


@pytest.mark.parametrize("mutation", ["missing", "unreviewed", "disputed", "not-independent", "stale-answer", "stale-labels"])
def test_missing_or_unreliable_judgment_blocks_score(tmp_path, mutation):
    data = fixture_data(tmp_path)
    if mutation == "missing": data[5].pop()
    if mutation == "unreviewed": data[5][0]["status"] = "unreviewed"
    if mutation == "disputed": data[5][0]["disagreement"] = True
    if mutation == "not-independent": data[5][0]["independent"] = False
    if mutation == "stale-answer": data[4][0]["answer"]["text"] = "Wrong source claim"
    if mutation == "stale-labels": data[5][0]["rubrics_sha256"] = "new-version"
    with pytest.raises(ValueError): summary(data)


def test_unexpected_refusal_fails_answerable_and_qualified_answer_passes(tmp_path):
    data = fixture_data(tmp_path, qualified=True)
    assert summary(data)["primary_macro"] == 1
    row, judgment = data[4][0], data[5][0]
    row["answer"]["confident"] = False
    row["answer"]["text"] = "I can't confirm that."
    judgment["observed_verdict"] = "refuse"
    judgment["binding_sha256"] = common.binding(data[3][row["id"]], row)
    assert summary(data)["primary_macro"] == 0.9
    refusal_data = fixture_data(tmp_path, refuse=True)
    assert summary(refusal_data)["semantic_questions"]["refusal_precision"] == 1


def test_sparse_families_never_substitute_for_primary_macro(tmp_path):
    data = fixture_data(tmp_path, n=2)
    result = summary(data)
    assert result["primary_macro"] is None
    assert result["all_sampled_macro"] == 1
    assert "primary semantic macro below floor or unavailable" in report.gate_failures(result)
    data[5][0]["complete"] = False
    assert any("sparse family" in text for text in report.gate_failures(summary(data)))


def test_cluster_weighting_and_paired_uncertainty_ignore_wording_count(tmp_path):
    data = fixture_data(tmp_path, n=3)
    questions, rubrics, manifest, _, results, audits = data
    rubrics[1]["cluster_id"] = rubrics[0]["cluster_id"]
    for question in questions[2:4]: question["group"] = rubrics[0]["cluster_id"]
    manifest["independent_cluster_count"] = 2
    manifest["family_counts"]["descriptions_product_purpose"]["independent_clusters"] = 2
    gold = common.normalize(questions, rubrics, manifest)
    for row, judgment in zip(results, audits): judgment["binding_sha256"] = common.binding(gold[row["id"]], row)
    audits[2]["complete"] = False
    result = report.summarize(gold, results, audits, manifest, "d", "r")
    assert result["all_sampled_macro"] == 0.75  # mean(cluster .5, cluster 1), not 2/3
    assert result["independent_clusters"] == 2
    assert report.interval({"family": [0, 1, 1]}) == report.interval({"family": [0, 1, 1]})


def test_missing_duplicate_and_cross_family_ids_rejected(tmp_path):
    questions, rubrics, manifest, *_ = fixture_data(tmp_path)
    with pytest.raises(ValueError): common.normalize(questions + [questions[0]], rubrics, manifest)
    with pytest.raises(ValueError): common.normalize(questions[:-1], rubrics, manifest)
    rubrics[1]["cluster_id"] = rubrics[0]["cluster_id"]
    rubrics[1]["family"] = "another_family"
    for question in questions[2:4]: question["group"] = rubrics[0]["cluster_id"]
    with pytest.raises(ValueError, match="multiple families"): common.normalize(questions, rubrics, manifest)


def test_blinded_review_pack_has_no_run_identity_and_cannot_be_edited(tmp_path):
    data = fixture_data(tmp_path, n=1)
    mapping, pack = audit.prepare(data[3], {"run_a": data[4], "run_b": data[4]}, "d", "r", seed=2)
    assert len(pack) == 4
    assert all("run" not in record and "id" not in record for record in pack)
    for record in pack: record["judgment"] = {key: value for key, value in data[5][0].items()
                                               if key not in ("id", "binding_sha256", "dataset_sha256", "rubrics_sha256")}
    collected = audit.collect(mapping, pack)
    assert set(collected) == {"run_a", "run_b"}
    pack[0]["answer"]["text"] = "Edited after blinding"
    with pytest.raises(ValueError, match="altered"): audit.collect(mapping, pack)


def test_source_hash_or_locator_failure_blocks_review_pack(tmp_path):
    data = fixture_data(tmp_path, n=1)
    (tmp_path / "source.md").write_text("Changed source")
    with pytest.raises(ValueError, match="source evidence"): audit.prepare(data[3], {"run_a": data[4]}, "d", "r")


def test_development_adapter_uses_explicit_schema_and_complete_claims(tmp_path):
    questions, blind, _, *_ = fixture_data(tmp_path, n=1)
    rubrics = []
    for question in questions:
        question["group"] = "s0"
        rubrics.append({"id": question["id"], "case_id": question["id"], "scenario_id": "s0", "cluster_id": "c0",
                        "family": blind[0]["family"], "question": question["question"], "as_of": question["as_of"],
                        "answerability": "answerable", "answer_kind": "qualified_correction", "required_verdict": "Correct the premise",
                        "claims": [{"claim_id": "claim1", "meaning": "Members pay $2."}], "required_claim_ids": ["claim1"],
                        "required_conditions": ["Mailed statements only"], "forbidden_claims": [], "source_refs": blind[0]["evidence"]})
    manifest = {"schema_version": common.DEV_SCHEMA, "counts": {"question_wordings": 2, "scenarios": 1,
                "independent_clusters": 1, "family_clusters": {blind[0]["family"]: 1}}}
    assert common.normalize(questions, rubrics, manifest)[questions[0]["id"]]["expected_verdict"] == "qualified_answer"
    rubrics[0]["required_claim_ids"].append("missing")
    with pytest.raises(ValueError, match="no meaning"): common.normalize(questions, rubrics, manifest)


def make_campaign(tmp_path):
    questions, rubrics, manifest, *_ = fixture_data(tmp_path, n=1)
    q, r, f, review = [tmp_path / name for name in ("questions.jsonl", "rubrics.jsonl", "freeze.json", "source-review.json")]
    common.write_rows(q, questions)
    common.write_rows(r, rubrics)
    manifest["sha256"] = {q.name: common.file_hash(q), r.name: common.file_hash(r)}
    common.write_json(f, manifest)
    common.write_json(review, {"status": "passed", "independent": True, "reviewer": "source-auditor",
                              "questions_sha256": common.file_hash(q), "rubrics_sha256": common.file_hash(r)})
    snapshots = tmp_path / "snapshots"
    snap = snapshots / "test"
    snap.mkdir(parents=True)
    (snap / "page.md").write_text("Artificial supplied source")
    (snap / "manifest.json").write_text(json.dumps({"pages": [{"file": "page.md"}]}))
    checkout = tmp_path / "repo"
    checkout.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args], stderr=subprocess.DEVNULL, text=True).strip()
    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.test")
    (checkout / "submission").mkdir()
    (checkout / "submission/solution.py").write_text("def build(): return None\n")
    git("add", "submission/solution.py")
    git("commit", "-m", "baseline")
    baseline = git("rev-parse", "HEAD")
    (checkout / "README").write_text("candidate")
    git("add", "README")
    git("commit", "-m", "candidate")
    candidate = git("rev-parse", "HEAD")
    root = tmp_path / "campaign"
    ledger.register(root, q, r, f, review, baseline, candidate, "frozen-policy-v1", snapshots)
    return root, checkout, snapshots, baseline, candidate, (q, r, f, review)


def test_ledger_freezes_exact_pair_and_does_not_reopen_on_commit_or_label(tmp_path):
    root, checkout, snapshots, baseline, candidate, paths = make_campaign(tmp_path)
    with pytest.raises(ValueError, match="already registered"):
        ledger.register(root, *paths, baseline, "a"*40, "changed-policy", snapshots)
    ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    with pytest.raises(ValueError, match="already consumed"):
        ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    with pytest.raises(ValueError, match="unknown comparison role"):
        ledger.reserve(root, "candidate-new-label", checkout, snapshots, Path(sys.executable))
    _, events, _ = ledger.read_campaign(root)
    assert [event["action"] for event in events] == ["registered", "started"]


def test_ledger_preflight_failures_retain_history_without_consuming_runtime(tmp_path):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    (checkout / "dirty").write_text("uncommitted")
    with pytest.raises(ValueError, match="dirty"):
        ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    (checkout / "dirty").unlink()
    ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    _, events, _ = ledger.read_campaign(root)
    assert [event["action"] for event in events] == ["registered", "preflight_failed", "started"]
    assert events[1]["answers_scored"] == 0 and events[1]["process_launched"] is False


def test_ledger_rejects_source_mutation_and_history_tampering(tmp_path):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    (snapshots / "test/page.md").write_text("Changed after freeze")
    with pytest.raises(ValueError, match="source corpus changed"):
        ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    events = common.rows(root / "events.jsonl")
    events[0]["action"] = "changed"
    (root / "events.jsonl").write_text("\n".join(json.dumps(row) for row in events))
    with pytest.raises(ValueError, match="event chain"): ledger.read_campaign(root)


def test_private_artifacts_cannot_enter_tracked_output_paths():
    with pytest.raises(ValueError, match="outside Git"):
        common.private_path(Path(__file__).resolve().parents[1] / "docs/private-gold.json")


@pytest.mark.parametrize("field,value", [("text", None), ("sources", {}), ("sources", [{"url": ""}]),
                                         ("sources", [{"url": "https://example.test", "quote": 12}]),
                                         ("conflict_note", {})])
def test_malformed_answer_cannot_pass_manual_flags(tmp_path, field, value):
    data = fixture_data(tmp_path, n=1)
    data[4][0]["answer"][field] = value
    data[5][0]["binding_sha256"] = common.binding(data[3][data[4][0]["id"]], data[4][0])
    with pytest.raises(ValueError, match="organizer"): summary(data)


def test_changed_scorer_is_not_a_new_attempt(tmp_path, monkeypatch):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    monkeypatch.setattr(ledger, "tools_hashes", lambda: {"different": "scorer"})
    with pytest.raises(ValueError, match="code changed"):
        ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    manifest = json.loads((root / "campaign.json").read_text())
    manifest["scorer_version"] = "new label"
    (root / "campaign.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest was modified"): ledger.read_campaign(root)


def test_failed_launched_process_consumes_slot_without_retry(tmp_path, monkeypatch):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    original = subprocess.run
    calls = []
    def failed_process(command, **kwargs):
        if len(command) > 1 and str(command[1]).endswith("_guarded_run_eval.py"):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1)
        return original(command, **kwargs)
    monkeypatch.setattr(ledger.subprocess, "run", failed_process)
    result = ledger.run(root, "candidate", checkout, snapshots, Path(sys.executable))
    assert result["slot_consumed"] and result["returncode"] == 1 and not result["retry_allowed"]
    assert len(calls) == 1 and calls[0][-2:] == ["--repeat-sample", "0"]
    with pytest.raises(ValueError, match="already consumed"):
        ledger.run(root, "candidate", checkout, snapshots, Path(sys.executable))


def test_report_cannot_substitute_unregistered_output(tmp_path):
    root, checkout, snapshots, baseline, candidate, paths = make_campaign(tmp_path)
    outputs = {}
    for role, sha in (("candidate", candidate), ("baseline", baseline)):
        subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", sha], check=True, capture_output=True)
        _, out = ledger.reserve(root, role, checkout, snapshots, Path(sys.executable))
        common.write_rows(out / "per_question.jsonl", [{"id": role}])
        ledger.finish(root, role, 0, out)
        outputs[role] = out / "per_question.jsonl"
    q, r, f, _ = paths
    commits = report.verify_campaign(root, q, r, f, outputs["candidate"], outputs["baseline"])
    assert commits["candidate"] == candidate
    with pytest.raises(ValueError, match="registered runtime outputs"):
        report.verify_campaign(root, q, r, f, outputs["baseline"], outputs["candidate"])


def test_lexical_trap_hint_does_not_override_reviewed_negated_correction(tmp_path):
    data = fixture_data(tmp_path, qualified=True)
    data[4][0]["trap_hits"] = ["unsupported premise quoted in a correction"]
    result = summary(data)
    assert result["primary_macro"] == 1
    assert result["semantic_questions"]["official_trap_hits"] == 1


def test_missing_citation_and_wrong_date_remain_zero_failure_safety_gates(tmp_path):
    data = fixture_data(tmp_path)
    row, judgment = data[4][0], data[5][0]
    row["answer"]["sources"] = []
    judgment["binding_sha256"] = common.binding(data[3][row["id"]], row)
    result = summary(data)
    assert result["semantic_questions"]["accepted_citation_failures"] == 1
    assert "accepted_citation_failures" in report.gate_failures(result)
    judgment["temporally_valid"] = False
    assert "accepted_temporal_failures" in report.gate_failures(summary(data))


def test_reviewed_number_free_contradictions_fail_wording_consistency(tmp_path):
    data = fixture_data(tmp_path)
    for index, text in enumerate(("The service is available.", "The service is not available.")):
        row, judgment = data[4][index], data[5][index]
        row["answer"]["text"] = text
        judgment["binding_sha256"] = common.binding(data[3][row["id"]], row)
        judgment["paraphrase_consistent"] = False
    assert summary(data)["primary_macro"] == 0.9


def test_correct_refusal_keeps_question_credit_when_partner_disagrees(tmp_path):
    data = fixture_data(tmp_path, n=1, refuse=True)
    row, judgment = data[4][1], data[5][1]
    row["answer"]["confident"] = True
    row["answer"]["text"] = "This unsupported service is available."
    judgment["observed_verdict"] = "answer"
    judgment["supported"] = False
    judgment["unsupported_claims"] = 1
    judgment["binding_sha256"] = common.binding(data[3][row["id"]], row)
    for review in data[5]:
        review["paraphrase_consistent"] = False
    result = summary(data)
    assert result["semantic_questions"]["passed_questions"] == 1
    assert result["semantic_questions"]["refusal_precision"] == 1
    assert result["all_sampled_macro"] == 0


def test_consistency_remains_a_scenario_check_with_correct_individual_answers(tmp_path):
    data = fixture_data(tmp_path, n=1)
    data[5][0]["paraphrase_consistent"] = False
    result = summary(data)
    assert result["semantic_questions"]["passed_questions"] == 2
    assert result["all_sampled_macro"] == 0


def test_ledger_rejects_event_tail_deletion(tmp_path):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    path = root / "events.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="event chain"):
        ledger.read_campaign(root)


def test_finish_cannot_bind_another_runs_output(tmp_path):
    root, checkout, snapshots, _, _, _ = make_campaign(tmp_path)
    _, out = ledger.reserve(root, "candidate", checkout, snapshots, Path(sys.executable))
    unrelated = tmp_path / "unrelated-output"
    unrelated.mkdir()
    common.write_rows(unrelated / "per_question.jsonl", [{"id": "unrelated"}])
    with pytest.raises(ValueError, match="registered output"):
        ledger.finish(root, "candidate", 0, unrelated)
    ledger.finish(root, "candidate", 1, out)


@pytest.mark.parametrize("identity", [True, " ", 7])
def test_adjudication_requires_named_reviewer(tmp_path, identity):
    data = fixture_data(tmp_path, n=1)
    data[5][0].update(status="adjudicated", adjudicator=identity)
    with pytest.raises(ValueError, match="adjudication provenance"):
        summary(data)
