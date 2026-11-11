# tests/test_95_harness_files.py
import json, re, subprocess
from pathlib import Path

def test_claude_md_is_short_and_has_the_commands():
    text = Path("CLAUDE.md").read_text()
    assert len(text.splitlines()) <= 60
    for cmd in ("python -m pytest -q", "python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl", "scripts/fresh_clone_check.sh"):
        assert cmd in text

def test_rules_have_paths_frontmatter():
    for name, glob in (("runtime", "submission/kb/**"), ("builders", "scripts/build_*.py"), ("tests", "tests/**"), ("data", "submission/data/**")):
        text = Path(f".claude/rules/{name}.md").read_text()
        assert text.startswith("---\npaths:") and glob in text

def test_settings_deny_kit_files_and_empty_attribution():
    s = json.loads(Path(".claude/settings.json").read_text())
    deny = set(s["permissions"]["deny"])
    for p in ("Edit(harness/**)", "Write(harness/**)", "Edit(eval/public_eval.jsonl)", "Edit(starter/**)", "Edit(snapshots_zip/**)", "Edit(snapshots/**)", "Bash(git push --force*)"):
        assert p in deny
    assert s["attribution"] == {"commit": "", "pr": ""}
    assert {h["matcher"] for h in s["hooks"]["PostToolUse"]} == {"Edit|Write"}

def test_hooks_exit_zero_and_print_one_line():
    for script, stdin in (("post_edit_tests.sh", '{"tool_input": {"file_path": "README.md"}}'), ("stop_eval_delta.sh", "{}"), ("session_start.sh", "{}")):
        r = subprocess.run(["bash", f".claude/hooks/{script}"], input=stdin, text=True, capture_output=True, timeout=60)
        assert r.returncode == 0 and r.stdout.count("kb-hook:") == 1

def test_commands_skill_and_agents_exist():
    for p in ("commands/eval.md", "commands/ask.md", "commands/fresh-clone.md", "commands/bench.md", "commands/go.md", "skills/kb-dev/SKILL.md", "agents/fact-auditor.md", "agents/eval-analyst.md", "agents/grader-sim.md", "agents/adversarial-reviewer.md"):
        text = Path(".claude", p).read_text(); assert text.startswith("---\n") and "description:" in text, p
    assert "## Gotchas" in Path(".claude/skills/kb-dev/SKILL.md").read_text()
