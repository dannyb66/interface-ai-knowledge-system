# tests/test_90_smoke.py
import json, os, subprocess, sys
from scoring import score_item

def test_public_eval_floor(tmp_path):
    # the harness as scripts/fresh_clone_check.sh runs it: a subprocess behind the socket guard, a fake key set
    env = {**os.environ, "OPENAI_API_KEY": "sk-fake"}
    subprocess.run([sys.executable, "scripts/_guarded_run_eval.py", "--submission", "submission", "--eval", "eval/public_eval.jsonl", "--out", str(tmp_path)], env=env, check=True, capture_output=True)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["errors"] == 0 and report["speed"]["p95_s"] < 0.5
    assert report["final_score"] >= 0.54, (report["final_score"], report["by_category"])  # floor lowered from 0.55 by user decision 2026-11-05

def test_public_refuse_items_score_one(public_items, ks_full):
    for it in public_items:
        if it["category"] == "should_refuse":
            assert score_item(it, ks_full.answer(it["question"], it.get("as_of")))["score"] == 1.0

def test_config_reads_only_one_env_var(monkeypatch):
    from kb.config import Config
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake"); monkeypatch.delenv("KB_LLM_INGEST", raising=False)
    assert Config.from_env().llm_ingest is False
    monkeypatch.setenv("KB_LLM_INGEST", "1")
    assert Config.from_env().llm_ingest is True and Config.from_env(llm_ingest=False).llm_ingest is False

# Gate review M4: a copy of submission/ outside the kit loads as run_eval.py loads it (its harness folder first on
# sys.path, then the team folder) in a fresh process run from outside the repo; with no harness anywhere, the import
# fails on the missing contract module, never with StopIteration.
def test_solution_loads_from_a_copy_outside_the_kit(tmp_path):
    import shutil
    team = tmp_path / "team"
    shutil.copytree("submission", team, ignore=shutil.ignore_patterns("__pycache__"))
    load = ("import importlib.util, sys; sys.path[:0] = {paths!r}; spec = importlib.util.spec_from_file_location("
            "'solution', {solution!r}); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "print(type(mod.build()).__name__)")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    def run(paths):
        code = load.format(paths=paths, solution=str(team / "solution.py"))
        return subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env, capture_output=True, text=True)
    graded = run([str(team), os.path.abspath("harness")])
    assert graded.returncode == 0 and graded.stdout.strip() == "KnowledgeSystem", graded.stderr[-600:]
    bare = run([str(team)])
    assert bare.returncode != 0 and "StopIteration" not in bare.stderr and "No module named 'contract'" in bare.stderr, bare.stderr[-600:]
