---
paths:
  - "submission/kb/**"
  - "submission/solution.py"
---

# Runtime rules (code the grader runs)

- No SDK imports (`anthropic`, `openai`, and the like) and no network calls; stdlib only.
- Read `os.environ` only in `kb/config.py`.
- Use an explicit sort key wherever a winner is chosen; never rely on dict, set or input order.
- Write 3.9-compatible syntax: no `match`, no `X | Y` types evaluated at runtime, no `zip(strict=)`, no `dataclass(slots=True)`.
- Templates render one resolved fact, never a list of candidates.
- Parse numbers the way `harness/scoring.py` `NUM_RE` does (same units, same comma and decimal handling).
- Write no files at runtime.
- `answer()` never raises: catch, warn once through `kb.errors`, and return the refusal.
