# tests/test_24_eval_keys.py
import importlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
import pytest
FIX = Path("tests/fixtures")

def test_eval_keys_match_fixture_or_listed_change(ks_full):
    sys.path.insert(0, "scripts")
    from dump_eval_keys import current_keys
    want = json.loads((FIX / "eval_keys.json").read_text())
    changes = json.loads((FIX / "eval_key_changes.json").read_text())
    got = current_keys(ks_full)
    assert sorted(got) == sorted(want) and len(got) == 120
    for k, q in got.items():
        if q != want[k]:
            assert k in changes and changes[k]["query"] == q and changes[k]["task"] and changes[k]["reason"], k
    stale = sorted(k for k in changes if got.get(k) != changes[k].get("query"))
    assert not stale, "entries of eval_key_changes.json that no longer match the parse: {}".format(stale)

def test_probe_corpus_is_deterministic(tmp_path):
    # M-3: the two runs pin different hash seeds (an inherited ambient seed would make them alike whatever the code)
    # and run at once; 60,000 questions in sorted order reach all 12 intents.
    from kb.lexicon import INTENTS
    procs = {}
    for seed in (1, 2):
        cmd = [sys.executable, "scripts/build_probe_corpus.py", "--out", str(tmp_path / str(seed)), "--limit", "60000"]
        with open(tmp_path / "{}.log".format(seed), "w") as log:  # the child keeps its own handle
            procs[seed] = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                           env=dict(os.environ, PYTHONHASHSEED=str(seed)))
    codes = {seed: proc.wait() for seed, proc in procs.items()}
    for seed, code in codes.items():
        assert code == 0, (tmp_path / "{}.log".format(seed)).read_text()[-3000:]
    a, b = (tmp_path / "1").read_bytes(), (tmp_path / "2").read_bytes()
    if a != b:  # name a few differing questions rather than diffing megabytes
        one, two = json.loads(a)["keys"], json.loads(b)["keys"]
        odd = sorted(q for q in set(one) | set(two) if one.get(q) != two.get(q))
        pytest.fail("seeds 1 and 2 differ on {} questions, e.g. {}".format(len(odd), odd[:3]))
    keys = json.loads(a)["keys"]
    intents = {key.split("|", 1)[0] for key in keys.values()}
    assert len(keys) == 60000 and intents == set(INTENTS), sorted(set(INTENTS) - intents)

# Fix round 1 (the review of Tasks 1 and 3): the probe workflow and the dump scripts.
def _script(name):
    if "scripts" not in sys.path:
        sys.path.insert(0, "scripts")
    return importlib.import_module(name)

def _build(*args, script="scripts/build_probe_corpus.py", seed=1):
    """The corpus builder under a pinned hash seed; the tail of its stderr is the failure message."""
    r = subprocess.run([sys.executable, str(script)] + [str(a) for a in args], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONHASHSEED=str(seed)))
    assert r.returncode == 0, r.stderr[-3000:]

def _scratch_tree(root):
    """A copy of the probe scripts and the submission whose lexicon lost "yield"; the harness modules are copied and
    the snapshots linked, so the scratch build writes nothing outside ``root``."""
    (root / "scripts").mkdir(parents=True)
    for name in ("build_probe_corpus.py", "diff_probe_keys.py"):
        shutil.copy(Path("scripts", name), root / "scripts" / name)
    shutil.copytree("submission", root / "submission", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "harness").mkdir()
    for path in sorted(Path("harness").glob("*.py")):
        shutil.copy(path, root / "harness" / path.name)
    (root / "snapshots").symlink_to(Path("snapshots").resolve(), target_is_directory=True)
    lexicon = root / "submission" / "kb" / "lexicon.py"
    lexicon.write_text(lexicon.read_text() + '\ndel SYNONYMS["yield"]  # the scratch lexicon: one phrase removed\n')
    return root

def test_removed_phrase_shows_as_changed_keys(tmp_path):  # I-1: the two-command workflow, OLD's questions reparsed
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    _build("--out", old, "--limit", 10000)
    scratch = _scratch_tree(tmp_path / "repo")
    _build("--out", new, "--limit", 10000, "--questions-from", old, script=scratch / "scripts" / "build_probe_corpus.py")
    r = subprocess.run([sys.executable, "scripts/diff_probe_keys.py", str(old), str(new)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr  # NEW parsed every question OLD holds
    changed, shared = map(int, re.match(r"changed (\d+) of (\d+)\n", r.stdout).groups())
    examples = [line for line in r.stdout.splitlines() if line.startswith("  ")]
    assert changed > 0 and shared == 10000 and examples and all("yield" in line for line in examples), r.stdout

def test_diff_exits_1_and_shows_questions_only_in_old(tmp_path, capsys):  # I-1: a removed phrase never hides
    diff = _script("diff_probe_keys")
    keys = {"question %d?" % i: "value|share_savings|apy|[]|None" for i in range(7)}
    for name, held in (("old", keys), ("new", {"question 0?": keys["question 0?"]})):
        (tmp_path / name).write_text(json.dumps({"version": 1, "count": len(held), "keys": held}))
    assert diff.main([str(tmp_path / "old"), str(tmp_path / "new")]) == 1
    out = capsys.readouterr().out
    shown = [line for line in out.splitlines() if line.startswith("  'question ")]
    assert "changed 0 of 1" in out and "6 only in OLD" in out and len(shown) == 5, out
    assert diff.main([str(tmp_path / "new"), str(tmp_path / "old")]) == 0  # only in NEW: added phrases, no failure

def test_limit_below_one_is_a_usage_error(tmp_path, capsys):  # M-1
    corpus = _script("build_probe_corpus")
    for limit in ("0", "-5"):
        with pytest.raises(SystemExit) as stop:
            corpus.main(["--out", str(tmp_path / "x.json"), "--limit", limit])
        assert stop.value.code == 2 and "--limit must be at least 1" in capsys.readouterr().err, limit
    assert not (tmp_path / "x.json").exists()

def test_an_unreadable_corpus_is_one_clean_line(tmp_path):  # M-2: e.g. results/p3/ missing in a fresh checkout
    (tmp_path / "bad.json").write_text("{not json")
    (tmp_path / "v2.json").write_text(json.dumps({"version": 2, "keys": {}}))
    cases = ((tmp_path / "missing.json", "cannot read"), (tmp_path / "bad.json", "not JSON"),
             (tmp_path / "v2.json", "not a version 1 probe corpus"))
    for path, words in cases:
        for cmd in (["scripts/diff_probe_keys.py", path, path],
                    ["scripts/build_probe_corpus.py", "--out", tmp_path / "x.json", "--questions-from", path]):
            r = subprocess.run([sys.executable] + [str(c) for c in cmd], capture_output=True, text=True)
            one_line = (r.returncode, r.stdout, len(r.stderr.splitlines())) == (2, "", 1)
            assert one_line and words in r.stderr and str(path) in r.stderr, (cmd, r.returncode, r.stderr)
    assert not (tmp_path / "x.json").exists()

def test_answers_dump_checks_the_facade(ks_full, tmp_path, capsys, monkeypatch):  # M-6: lint or cache regressions
    from types import SimpleNamespace
    from kb.compose import refusal
    dump = _script("dump_eval_keys")
    answers = dump.current_answers(ks_full)
    assert len(answers) == 60 and all(a["facade_same"] for a in answers.values())
    wrong = SimpleNamespace(_parse=ks_full._parse, store=ks_full.store, registry=ks_full.registry,
                            answer=lambda question, as_of=None: refusal("that"))  # a facade gone wrong
    monkeypatch.setattr(dump, "build_system", lambda: wrong)
    assert dump.main(["--answers", str(tmp_path / "answers.json")]) == 1
    assert "dup-001" in capsys.readouterr().err
    assert json.loads((tmp_path / "answers.json").read_text())["dup-001"]["facade_same"] is False

def test_answers_dump_checks_a_repeat_call(ks_full, monkeypatch):  # M-6: the cache-hit path the harness repeats take
    from kb.compose import refusal
    stale = refusal("that")
    class StaleHits(dict):  # the facade's answer cache, but a hit returns another Answer than the one stored
        def get(self, key, default=None):
            return stale if key in self else default
    monkeypatch.setattr(ks_full, "_answers", StaleHits())
    answers = _script("dump_eval_keys").current_answers(ks_full)
    assert answers["dup-001"]["facade_same"] is False
    assert not any(a["facade_same"] for a in answers.values() if a["text"] != stale.text)

def test_question_module_is_split():  # Phase 3 Task 2: no behaviour change, so the fixture test above still holds
    from kb.qslots import attribute, keyword_intent, slots, superlative, url_cue
    q, s = (Path("submission/kb") / n for n in ("question.py", "qslots.py"))
    assert len(q.read_text().splitlines()) <= 420 and len(s.read_text().splitlines()) <= 320
    from kb.normalize import branch_name, question_dates, question_term  # moved there by the gate review round
    assert question_dates("between june and august 2026") == ["2026-06-30", "2026-08-31"]  # (pin)
    from kb import qslots, question
    for name in ("Hit", "attribute", "keyword_intent", "seq", "slots"):  # what question.py imports back
        assert getattr(question, name) is getattr(qslots, name), name
    assert question.__all__ == ["INTENTS", "SYNONYMS", "Query", "parse"]

def test_resolve_helpers_are_split_and_reexported():  # Phase 3 Task 3b: no behaviour change, as above
    import kb.plans, kb.resolve
    names = ("_bounds", "_date_tokens", "_name_numbers", "_refusal", "_refusal_span", "_sources", "join_notes",
             "_SPAN_CAP", "_UNSAFE_RE", "_CUE_RE", "_LEAD_RE", "_VERB_RE", "_LINK_RE", "_DETERMINERS", "_OWNERS", "Days")
    for n in names:  # every moved name is re-exported as the same object
        assert getattr(kb.resolve, n) is getattr(kb.plans, n), n
    import kb.conflicts
    assert kb.conflicts.join_notes is kb.plans.join_notes
    import ast
    tree = ast.parse(Path("submission/kb/plans.py").read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not {m for m in imported if m and ("resolve" in m or "conflicts" in m)}, imported  # no cycle at any depth
    lines = {n: len(Path("submission/kb", n).read_text().splitlines()) for n in ("resolve.py", "plans.py")}
    assert lines["resolve.py"] <= 490 and lines["plans.py"] <= 130, lines  # the 500-line rule is the real limit
