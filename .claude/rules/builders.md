---
paths:
  - "scripts/build_*.py"
---

# Builder rules (offline scripts that produce `submission/data/`)

- Set `KB_LLM_INGEST=1` only when running a builder here; without it a builder makes no LLM call, and nothing under `submission/` ever calls one.
- Every emitted number must appear verbatim in its source block, or the row is dropped.
- Write outputs only under `submission/data/`, as plain JSON with a one-line version header.
