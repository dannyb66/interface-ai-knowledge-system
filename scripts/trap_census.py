"""The trap census: the value of every prose or curated fact checked against every ``must_not_include`` token.

    python scripts/trap_census.py

Builds the system from every crawl under ``snapshots/`` (ingestion's stdout goes to stderr), then checks the
``value_text`` of every fact of every crawl whose extractor is in ``kb.resolve.STRICT_EXTRACTORS`` (``prose`` and
``curated``: the facts whose plans the strict lint reads) against every ``must_not_include`` token of the public and
dev items (``eval/public_eval.jsonl`` and ``eval/dev_extra.jsonl``, read by name: nothing else under ``eval/``) with
the scorer's own ``contains``, so a unit-less number token (``2020``, ``294``) matches any number of that value.

Prints one tab-separated row per collision, each once, sorted: product id, attribute, value text, token and item
id; then one count line. Writes no file: a collision a ruling accepts goes into ``tests/fixtures/trap_allowlist.json``
by hand, keyed ``<product_id>|<attribute>|<token>`` with the ruling's reason as its value, and
``tests/test_31_compose_p3.py`` fails on every collision the allowlist lacks. The repo root comes from this file's
location, so any working directory works.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission", "scripts"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

from dump_eval_keys import build_system, load_items  # noqa: E402  (the five crawls; the 60 public and dev items)
from kb.resolve import STRICT_EXTRACTORS  # noqa: E402  (one set for the lint and the census)
from kb.store import FactStore  # noqa: E402
from kb.types import Fact  # noqa: E402
from scoring import contains  # noqa: E402

Row = Tuple[str, str, str, str]  # ("<product_id>|<attribute>", value_text, token, item id)


def strict_facts(store: FactStore) -> List[Fact]:
    """Every fact of every crawl whose extractor is in ``STRICT_EXTRACTORS``, oldest crawl first."""
    return [f for snapshot_id, _ in store.snapshots() for facts in store.by_product_attr[snapshot_id].values()
            for f in facts if f.extractor in STRICT_EXTRACTORS]


def collisions(store: FactStore, items: Sequence[dict]) -> List[Row]:
    """``("<product_id>|<attribute>", value_text, token, item id)`` for each prose or curated fact whose value text
    holds a ``must_not_include`` token of an item (``scoring.contains``); each row once, sorted."""
    rows = {(f.product_id + "|" + f.attribute, f.value_text, token, str(item["id"]))
            for f in strict_facts(store) for item in items for token in item.get("must_not_include") or ()
            if contains(f.value_text, token)}
    return sorted(rows, key=lambda row: row)


def main(argv: Optional[List[str]] = None) -> int:
    argparse.ArgumentParser(description="Print each prose or curated fact value that holds a must_not_include "
                                        "token of a public or dev item.").parse_args(argv)
    store = build_system().store
    items = load_items()
    rows = collisions(store, items)
    for key, value_text, token, item_id in rows:
        print("\t".join(key.split("|", 1) + [value_text, token, item_id]))
    tokens = sum(len(item.get("must_not_include") or ()) for item in items)
    print("trap_census: {} collisions; {} prose or curated facts, {} must_not_include tokens, {} items".format(
        len(rows), len(strict_facts(store)), tokens, len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
