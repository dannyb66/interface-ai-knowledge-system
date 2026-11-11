# Locked set: an independent probe of prose coverage, one question for each of 30 pages drawn at random from snapshot 05_2026-09-28_latest.
Seed 20261104: `python scripts/sample_pages.py --snapshot 05_2026-09-28_latest --n 30 --seed 20261104` regenerates the page list; lock-001..lock-030 follow its order.
Written before the extractor existed: every must_include token is copied verbatim from its page, not from any system output.
Scored once per phase, at the end of the phase, never as a tuning loop.
Never inspect per-item failures mid-phase; read only the aggregate score until the phase closes.
lock-023 and lock-027 (business-resources tag listing pages whose date lists are not filtered by tag) were removed after review, leaving 28 items whose ids keep their sample-order numbers.
