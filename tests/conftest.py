"""Shared fixtures and fact helpers. Paths are relative to the repo root, where pytest runs."""
import dataclasses
import json
import re
from pathlib import Path

import pytest
from run_eval import load_snapshots


@pytest.fixture
def selftest_snapshots():
    return load_snapshots(Path("harness/selftest/snapshots"))


@pytest.fixture
def public_items():
    lines = Path("eval/public_eval.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture
def ks():
    import solution  # imported here so a missing submission fails the test, not collection

    return solution.build()


def ingest_all(snapshots):
    """The facade as the harness drives it: ``solution.build()``, then ``ingest`` per crawl in the given order."""
    import solution  # imported here so a broken submission fails the tests, not collection

    ks = solution.build()
    for snapshot in snapshots:
        ks.ingest(snapshot)
    return ks


def build_store(root=Path("snapshots")):
    """Every rules fact of every crawl under ``root`` in one finalised ``FactStore``, built by the facade's own
    ``ingest`` (page typing, legacy aliases, extraction, ``add`` once per crawl, ``finalize``), so the resolver and
    composer tests read exactly the store the graded path answers from."""
    return ingest_all(load_snapshots(root)).store


@pytest.fixture(scope="session")
def real_snapshots():
    """The five real crawls, oldest first, loaded once per session."""
    return load_snapshots(Path("snapshots"))


@pytest.fixture(scope="session")
def ks_full(real_snapshots):
    """``solution.build()`` with every real crawl ingested oldest first."""
    return ingest_all(real_snapshots)


@pytest.fixture(scope="session")
def store_full(ks_full):
    """The store of ``ks_full``: one ingest per session serves the resolver, composer and facade tests."""
    return ks_full.store


def make_fact(product_id, attribute, value_text, *, snapshot_id="05_2026-09-28_latest",
              url="https://www.dupaco.com/rates", page_type="rate_sheet", authority=3, extractor="rules", claim=None,
              published=None, event=None, block=0, row=0, value=None, unit="pct", **quals):
    """One fact as a rules table row read on ``url`` (also its canonical URL) in ``snapshot_id``, fetched on the
    crawl date the id embeds, quoted ``| row |``, confidence 1.0; ``quals`` are its qualifiers. ``claim`` ``None``
    is ``ClaimType.RATE``. The defaults are the old ``test_30_compose._fact``."""
    from kb.types import ClaimType, Fact, Source, make_key  # here, so a broken submission fails the test

    key = make_key(product_id, attribute, quals)
    day = re.search(r"\d{4}-\d{2}-\d{2}", snapshot_id)
    fetched_at = day.group(0) if day else "2026-09-28"
    src = Source(url, url, page_type, authority, snapshot_id, fetched_at, block, row, "| row |")
    return Fact(key, product_id, attribute, key[2], value, value_text, unit, claim or ClaimType.RATE, None, event,
                published, src, extractor, 1.0)


def single_plan(intent, fact, permitted=frozenset(), **fields):
    """A confident one-fact plan answered from the fact's own crawl; ``fields`` replace other ``AnswerPlan`` fields."""
    from kb.types import AnswerPlan

    plan = AnswerPlan(intent, (fact,), permitted, (fact.source,), True, None, fact.source.snapshot_id)
    return dataclasses.replace(plan, **fields)
