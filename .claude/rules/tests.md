---
paths:
  - "tests/**"
---

# Test rules

- Name files `test_NN_<topic>.py` (two-digit NN, ordered by pipeline stage).
- Use the `harness/selftest` fixtures (`selftest_snapshots` in `tests/conftest.py`) for fast tests.
- No network. `scripts/_guarded_run_eval.py` is the socket guard (any socket call raises `RuntimeError`); run harness checks through it, never around it.
