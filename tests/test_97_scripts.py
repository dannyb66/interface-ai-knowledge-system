# tests/test_97_scripts.py
import importlib.util, json, os, re, shutil, subprocess, sys, types
from pathlib import Path

import pytest

def test_ask_explain_prints_key_and_winner():
    r = subprocess.run([sys.executable, "scripts/ask.py", "What is the APY on Dupaco's 17-month special certificate?", "--explain"], capture_output=True, text=True, check=True)
    assert "canonical_key" in r.stdout and "winner" in r.stdout and "4.10%" in r.stdout

def test_eval_sh_quick_writes_stamp():
    # Strengthened in place. This is the Stop hook's own command line (no --out), so the report lands in results/
    # beside the stamp. Both files are back-dated first: test_95's hook run touches them before this test starts.
    stamp, report = Path("results/.last_eval"), Path("results/report.json")
    stamp.parent.mkdir(exist_ok=True)
    for path in (stamp, report):
        path.touch()
        os.utime(path, (1, 1))
    r = subprocess.run(["bash", "scripts/eval.sh", "--quick"], capture_output=True, text=True, check=True)
    assert stamp.stat().st_mtime > 1 and report.stat().st_mtime > 1
    assert "final_score" in r.stdout and "missed" in r.stdout
    data = json.loads(report.read_text())
    assert data["questions"] == 40 and data["consistency"]["repeat_checks"] == 0  # public set, --repeat-sample 0
    lines = r.stdout.splitlines()
    summary = next(i for i, line in enumerate(lines) if line.startswith("misses: "))
    n_miss, n_items = map(int, re.match(r"misses: (\d+) of (\d+) items", lines[summary]).groups())
    assert n_items == 40
    assert lines[summary + 1].split() == ["id", "category", "weight", "missed", "trap_hits", "refusal?", "score"]
    rows = lines[summary + 2 : next(i for i, line in enumerate(lines) if line.startswith("files: "))]
    # dup-005 has no must_include tokens, so it misses whatever the system answers: a row that outlives Task 11
    assert len(rows) == n_miss and any(row.split()[:2] == ["dup-005", "list_completeness"] for row in rows)

# Stands in for scripts/_guarded_run_eval.py: writes a minimal report wherever --out says and exits 0, so the
# stamp rule below runs without a real harness run. Its arguments go to argv.json beside it, never under --out:
# --holdout and --locked remove their --out directory again. With --conflicts-gold the report gains a conflicts block.
FAKE_RUNNER = """\
import json, os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "argv.json"), "w") as fh:
    json.dump(sys.argv[1:], fh)
out = sys.argv[sys.argv.index("--out") + 1]
os.makedirs(out, exist_ok=True)
row = {"id": "x-1", "category": "c", "weight": 1.0, "score": 0.0, "missed": ["t"], "trap_hits": [], "answer": {"text": "", "confident": False}}
with open(os.path.join(out, "per_question.jsonl"), "w") as fh:
    fh.write(json.dumps(row))
report = {"final_score": 0.5, "qa_score": 0.5, "questions": 1, "errors": 0}
if "--conflicts-gold" in sys.argv:
    report["conflicts"] = {"gold": 4, "submitted": 2, "matched": 1, "recall": 0.25, "precision": 0.5, "f1": 0.3333, "resolution_accuracy": 1.0}
with open(os.path.join(out, "report.json"), "w") as fh:
    json.dump(report, fh)
"""

@pytest.fixture
def fake_root(tmp_path):
    """A repo root holding a copy of eval.sh and the stand-in runner, so eval.sh runs here without a harness run."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy("scripts/eval.sh", root / "scripts" / "eval.sh")
    shutil.copy("scripts/proxy_report.py", root / "scripts" / "proxy_report.py")
    (root / "eval/proxy").mkdir(parents=True)
    for name in ("proxy", "holdout"):
        (root / "eval/proxy" / (name + ".jsonl")).write_text(
            json.dumps({"id": "x-1", "family": "synthetic"}) + "\n", encoding="utf-8")
    (root / "scripts" / "_guarded_run_eval.py").write_text(FAKE_RUNNER)
    return root

def _eval_sh(root, *args):
    # cwd is the repo root, so a relative --out such as "results" names its results/
    return subprocess.run(["bash", str(root / "scripts" / "eval.sh")] + list(args), cwd=root, capture_output=True, text=True, check=True)

def test_eval_sh_touches_the_stamp_only_when_the_report_lands_in_results(fake_root, tmp_path):
    stamp, elsewhere = fake_root / "results" / ".last_eval", tmp_path / "elsewhere"
    cases = [  # (arguments, does the run touch the stamp?)
        ([], True), (["--public"], True), (["--quick"], True),
        (["--quick", "--out", "results"], True), (["--quick", "--out", str(fake_root / "results") + "/"], True),
        (["--quick", "--out", str(elsewhere)], False), (["--public", "--out", str(elsewhere)], False),
        (["--dev"], False), (["--locked"], False), (["--proxy"], False), (["--holdout"], False), (["--conflicts"], False),
    ]
    for args, touched in cases:
        stamp.unlink(missing_ok=True)
        _eval_sh(fake_root, *args)
        assert stamp.exists() is touched, args

def test_eval_sh_dev_stays_out_of_results_and_locked_prints_one_line(fake_root):
    _eval_sh(fake_root, "--dev")
    assert (fake_root / "results" / "dev" / "report.json").exists()
    assert not (fake_root / "results" / "report.json").exists()  # the public report the Stop hook reads
    lines = _eval_sh(fake_root, "--locked").stdout.splitlines()
    assert len(lines) == 1 and lines[0].startswith("locked final_score=")  # no miss table, no per-item row

def _runner_args(root):
    """The flag -> value pairs the stand-in runner was last called with (eval.sh passes each flag with one value)."""
    argv = json.loads((root / "scripts" / "argv.json").read_text())
    return {flag: Path(value).resolve() if flag != "--repeat-sample" else value for flag, value in zip(argv[::2], argv[1::2])}

def test_eval_sh_proxy_holdout_and_conflicts_modes(fake_root):
    root = fake_root.resolve()
    r = _eval_sh(fake_root, "--proxy")
    args = _runner_args(fake_root)
    assert (args["--eval"], args["--out"]) == (root / "eval" / "proxy" / "proxy.jsonl", root / "results" / "proxy")
    assert "--conflicts-gold" not in args and "misses: 1 of 1 items" in r.stdout  # the harness summary and the miss table
    lines = _eval_sh(fake_root, "--holdout").stdout.splitlines()
    args = _runner_args(fake_root)
    assert args["--eval"] == root / "eval" / "proxy" / "holdout.jsonl" and "--conflicts-gold" not in args
    assert lines[0].startswith("holdout final_score=")
    assert "family synthetic count=1 qa=0.0000 traps=0" in lines
    assert all("x-1" not in line and "misses:" not in line for line in lines)  # aggregates only
    assert not args["--out"].exists()  # its per-item rows went to a temp directory that is gone again
    lines = _eval_sh(fake_root, "--conflicts").stdout.splitlines()
    args = _runner_args(fake_root)
    assert (args["--eval"], args["--out"]) == (root / "eval" / "public_eval.jsonl", root / "results" / "conflicts")
    assert args["--conflicts-gold"] == root / "eval" / "conflicts_gold_dev.json"
    assert lines == ["conflicts gold=4 submitted=2 matched=1 precision=0.5000 recall=0.2500 f1=0.3333 "
                     "resolution_accuracy=1.0000 final_score=0.5000"]

def test_eval_sh_rejects_mixed_modes_and_unknown_flags():
    # exit 2 before any harness run: the harness prints "ingest ..." to stdout first, so empty stdout proves it never ran
    for args in (["--quick", "--dev"], ["--bogus"], ["--proxy", "--holdout"]):
        r = subprocess.run(["bash", "scripts/eval.sh"] + args, capture_output=True, text=True)
        assert r.returncode == 2 and r.stdout == "" and "usage:" in r.stderr, args

def test_bench_reports_p95():
    r = subprocess.run([sys.executable, "scripts/bench.py", "--n", "40"], capture_output=True, text=True, check=True)
    assert "p95" in r.stdout and "answer" in r.stdout

def test_sample_pages_finds_the_snapshots_from_any_cwd(tmp_path):
    # the regeneration command in eval/locked/README.md must not depend on where it is run from
    if not Path("snapshots/05_2026-09-28_latest/manifest.json").is_file():
        pytest.skip("snapshots are not unpacked yet")
    script = Path("scripts/sample_pages.py").resolve()
    r = subprocess.run([sys.executable, str(script), "--snapshot", "05_2026-09-28_latest", "--n", "1", "--seed", "20261104"], cwd=tmp_path, capture_output=True, text=True, check=True)
    url, file = r.stdout.rstrip("\n").split("\t")
    assert url.startswith("http") and file

def _load_script(name):
    # scripts/ is not on pythonpath, so import by path; a fresh module per call keeps monkeypatching local to a test
    spec = importlib.util.spec_from_file_location("kb_script_" + name, Path("scripts") / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_bench_percentile_matches_the_graders_rule():
    from scoring import score_speed
    bench = _load_script("bench")
    for n in (1, 2, 40, 41):
        # integer-valued so rounding cannot hide an index error; descending so the sort matters (n=41 tells int() from round())
        latencies = [float(i) for i in range(n, 0, -1)]
        graded = score_speed(latencies)
        assert round(bench.percentile(latencies, 0.5), 2) == graded["p50_s"], n
        assert round(bench.percentile(latencies, 0.95), 2) == graded["p95_s"], n

class _Facade:
    """answer() is instant; explain() raises on the numbered calls in ``fail_on`` and reports stage timings otherwise."""

    def __init__(self, fail_on=(), timings=None):
        self.fail_on, self.timings, self.calls = set(fail_on), timings, 0

    def ingest(self, snapshot):
        pass

    def answer(self, question, as_of=None):
        return None

    def explain(self, question, as_of=None):
        self.calls += 1
        if self.calls in self.fail_on:
            raise ValueError("boom %d" % self.calls)
        return {} if self.timings is None else {"timings_ms": self.timings}

def _run_bench(monkeypatch, capsys, facade):
    bench = _load_script("bench")
    monkeypatch.setattr(bench, "solution", types.SimpleNamespace(build=lambda: facade))
    monkeypatch.setattr(bench, "load_snapshots", lambda root: [])
    code = bench.main(["--n", "3"])
    out, err = capsys.readouterr()
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.split()[:2] == ["stage", "n"])
    return code, {line.split()[0]: int(line.split()[1]) for line in lines[start + 1:]}, err

def test_bench_reports_explain_failures(monkeypatch, capsys):
    stages = {"parse": 1.0, "resolve": 2.0, "render": 3.0}
    code, rows, err = _run_bench(monkeypatch, capsys, _Facade(fail_on={1, 2, 3}, timings=stages))
    assert code == 1 and rows == {"answer": 3}, "every explain() raised"
    assert "explain() raised for 3 of 3: ValueError: boom 1" in err and "no timings_ms" not in err
    code, rows, err = _run_bench(monkeypatch, capsys, _Facade(fail_on={2}, timings=stages))
    assert code == 1 and rows == {"parse": 2, "resolve": 2, "render": 2, "answer": 3}, "one explain() raised"
    assert "explain() raised for 1 of 3: ValueError: boom 2" in err
    code, rows, err = _run_bench(monkeypatch, capsys, _Facade(timings=stages))
    assert code == 0 and err == "" and rows == {"parse": 3, "resolve": 3, "render": 3, "answer": 3}, "all fine"
    code, rows, err = _run_bench(monkeypatch, capsys, _Facade())
    assert code == 0 and rows == {"answer": 3} and "no timings_ms" in err, "explain() without timings_ms"
