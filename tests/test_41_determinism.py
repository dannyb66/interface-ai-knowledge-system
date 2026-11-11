"""Conflict and answer determinism plus the fresh-clone curation gate."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CODE = """
import contextlib, dataclasses, json, sys
from pathlib import Path
sys.path[:0] = ['submission', 'harness']
import solution
from run_eval import load_snapshots
ks = solution.build()
with contextlib.redirect_stdout(sys.stderr):
    for snapshot in load_snapshots(Path('snapshots')):
        ks.ingest(snapshot)
print(json.dumps([dataclasses.asdict(c) for c in ks.conflicts()], sort_keys=True))
"""


def test_conflicts_identical_across_hash_seeds():
    outputs = [subprocess.run([sys.executable, "-c", CODE], cwd=ROOT,
                             env={**os.environ, "PYTHONHASHSEED": seed, "OPENAI_API_KEY": "sk-fake"},
                             capture_output=True, text=True, check=True).stdout
               for seed in ("0", "12345")]
    expected = len(json.loads((ROOT / "submission/data/conflicts_curated.json").read_text(encoding="utf-8"))["conflicts"])
    assert outputs[0] == outputs[1]
    assert len(json.loads(outputs[0])) == expected


def test_public_answers_identical_across_hash_seeds(tmp_path):
    outputs = []
    for seed in ("0", "12345"):
        out = tmp_path / seed
        subprocess.run([sys.executable, "scripts/_guarded_run_eval.py", "--submission", "submission",
                        "--eval", "eval/public_eval.jsonl", "--out", str(out), "--repeat-sample", "0"],
                       cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed}, check=True, capture_output=True)
        outputs.append([{key: value for key, value in json.loads(line).items() if key != "latency_s"}
                        for line in (out / "per_question.jsonl").read_text(encoding="utf-8").splitlines()])
    assert outputs[0] == outputs[1]


def test_fresh_clone_rejects_missing_or_partial_curated_verification(tmp_path):
    # Execute the clone script's validator on adversarial checker output. A checker
    # that exits successfully after silently dropping entries must still fail.
    script = (ROOT / "scripts/fresh_clone_check.sh").read_text(encoding="utf-8")
    assert "scrubbed .venv/bin/python scripts/check_curated.py" in script
    validator = re.search(r'\.venv/bin/python -I - "\$TMP/curated.log" <<\'PY\'\n(.*?)\nPY', script, re.S).group(1)
    data = tmp_path / "submission/data"
    data.mkdir(parents=True)
    (data / "conflicts_curated.json").write_text(json.dumps({"conflicts": [{}, {}]}), encoding="utf-8")
    log = tmp_path / "curated.log"
    for text, accepted in (("curated: 2/2 verified\n", True), ("curated: 1/2 verified\n", False),
                           ("curated: 1/1 verified\n", False), ("", False)):
        log.write_text(text, encoding="utf-8")
        run = subprocess.run([sys.executable, "-I", "-", str(log)], input=validator, cwd=tmp_path,
                             text=True, capture_output=True)
        assert (run.returncode == 0) is accepted
