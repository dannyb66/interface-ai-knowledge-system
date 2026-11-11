---
description: Ask the knowledge system one question and show its answer, sources and winning fact
argument-hint: '"<question>" [--as-of YYYY-MM-DD] [--explain]'
allowed-tools: Bash(python scripts/ask.py *), Read
---

Run `python scripts/ask.py $ARGUMENTS` from the repo root. The question is the first argument and stays quoted; `--as-of` takes an ISO date; `--explain` adds the `explain()` dict as indented JSON.

Report:
1. The answer text, the `confident` flag and the sources.
2. With `--explain`: the `canonical_key`, the `snapshot_id`, the `winner` fact (value, quote, source page, effective date) and the top candidates that lost, with their ranks.

Then judge the answer against the kb-dev Gotchas: one resolved fact, units on every number, no stray number, and for a refusal `confident=False` plus a refusal phrase. If the answer is wrong, re-run with `--explain` and name the failing stage (parse, resolve or render). Never edit files in this command.
