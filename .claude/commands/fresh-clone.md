---
description: Clone the committed repo, build a clean venv and run the public eval under the socket guard
argument-hint: "[--python PATH] [--repo PATH] [--floor SCORE]"
allowed-tools: Bash(scripts/fresh_clone_check.sh), Bash(scripts/fresh_clone_check.sh *), Read
---

Run `scripts/fresh_clone_check.sh $ARGUMENTS` from the repo root. It clones the committed state, so uncommitted work is not tested: say so when `git status --short` shows changes under `submission/` or `scripts/`. The venv build and `pip install` take a few minutes, so run it in the foreground with the longest Bash timeout.

Success prints `fresh-clone: OK score=... p95=...s install=...s`. Failure prints one `fresh-clone: FAIL ...` line on stderr.

Report that line. On a FAIL name the gate that broke (`errors`, `ingest_over_limit`, `p95_s` below 0.5, or the score floor taken from `results/baseline.json`) and the likely cause. Never edit files in this command.
