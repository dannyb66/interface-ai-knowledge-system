---
description: Benchmark answer latency with p50 and p95 per stage
argument-hint: "[--n 200]"
allowed-tools: Bash(python scripts/bench.py), Bash(python scripts/bench.py *), Read
---

Run `python scripts/bench.py $ARGUMENTS` from the repo root. It times `parse`, `resolve`, `render` and end-to-end `answer` over the public questions (the `explain()` timings) and prints p50 and p95 for each.

Summarise as one small table plus a verdict:
- The design target is an answer p95 under 50 ms; the scorer gives full speed credit up to 2 s and the fresh-clone check fails at 0.5 s.
- Name the slowest stage and what probably dominates it.
- If p95 is far above p50, look for work in `answer()` that belongs in `ingest()`.

Never edit files in this command.
