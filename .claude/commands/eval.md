---
description: Run the eval and show the misses per question with the likely failing stage
argument-hint: "[--public|--dev|--locked|--quick] [--out DIR]"
allowed-tools: Bash(scripts/eval.sh), Bash(scripts/eval.sh *), Read
---

Run `scripts/eval.sh $ARGUMENTS` from the repo root; with no arguments it scores the public set. It runs `harness/run_eval.py`, then prints the summary, a table of misses (`id, category, weight, missed, trap_hits, refusal?, score`) and the per-category scores. Only `--public` and `--quick`, and only when the report lands in `results/` (no `--out`), touch `results/.last_eval`.

Summarise in under 15 lines:
1. `final_score` (the dev set reports `qa_score`) and its delta against `public_final_score` in `results/baseline.json`.
2. The misses ordered by weight, trap hits first (one trap token zeroes an item), each with its category and the likely stage: extract, parse, resolve, render or refusal.
3. The one miss to fix next and the file to read first.

Confirm a stage with `/ask "<question>" --explain` before proposing an edit. Never edit files in this command.

With `--locked`, report only the aggregate score. Do not list, quote or analyse its misses: `eval/locked/README.md` says it is scored once per phase and never used as a tuning loop.
