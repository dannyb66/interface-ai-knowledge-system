# as_of contract

Copied from the as_of bullet of Global Constraints in `docs/superpowers/plans/2026-11-04-phase-2-facts-and-answers.md`.

- The argument beats a date in the question.
- `as_of=None` means the latest snapshot.
- A date after the last crawl means the latest snapshot.
- A date before the first crawl answers from the earliest snapshot with a digit-free `conflict_note`.
- A malformed date returns the refusal.
- Facts whose `effective_date` is after `as_of` are excluded.

Snapshots, oldest first: `01_2026-05-12_baseline`, `02_2026-05-19_recrawl`, `03_2026-06-09_recrawl`, `04_2026-08-27_rebaseline`, `05_2026-09-28_latest`.

## Pinned examples

- `2026-05-31`, `05/31/2026`, `2026-05` and "May 2026" resolve to the same snapshot (Task 8 `test_as_of_formats_resolve_to_same_snapshot`).
- as_of 2026-05-31 selects `02_2026-05-19_recrawl`, so the 10-month fixed jumbo special answers 3.90% (Task 9 `test_as_of_uses_the_snapshot_in_force`).
- Phrase it "As of May 2026 the 10-month fixed jumbo certificate special paid 3.90% APY." and never quote the later value (formatting contract, rule 11).
