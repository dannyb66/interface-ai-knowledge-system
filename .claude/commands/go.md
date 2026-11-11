---
description: Ship the current change with tests, quick eval, /simplify, commit and PR
argument-hint: "[commit subject]"
allowed-tools: Bash(python -m pytest *), Bash(scripts/eval.sh *), Bash(git status*), Bash(git diff*), Bash(git add *), Bash(git commit *), Bash(git push -u origin HEAD), Bash(gh pr create *), Skill(simplify)
---

Ship the work on the current branch. Run the steps in order and stop at the first red step, reporting it.

1. `python -m pytest -q`. Any failure stops the command.
2. `scripts/eval.sh --quick`. Report `final_score` and its delta against `public_final_score` in `results/baseline.json`; if it fell, stop and ask.
3. Invoke `/simplify` on the diff. If it changed files, run step 1 again.
4. Commit with explicit paths, never `git add -A` (untracked data such as `snapshots/` stays out). The message is a conventional commit, `type(scope): subject` in the imperative, taken from `$ARGUMENTS` when given and from the diff otherwise. No `Co-Authored-By` or other trailer (`attribution.commit` is empty), no `--no-verify`, no secrets or `.env` files.
5. If the branch has no upstream, run `git push -u origin HEAD` (never force). Then `gh pr create --fill --base main`.

Finish with the PR URL, the test and eval lines, and what `/simplify` changed.
