"""Offline census of conflict candidates in a finalised fact store, the raw material of the curated conflicts list.

    python scripts/build_conflict_candidates.py [--out results/p3/conflict_candidates.json]

Reads ``FactStore.by_key`` crawl by crawl (``FactStore.snapshots()`` gives the order) and skips facts without a
number. Two kinds of candidate:

- ``in_force``: in one crawl, one match key holds two or more distinct ``(unit, value)`` pairs on two or more pages;
- ``cross_crawl``: between two consecutive crawls, one match key on one page shows one value before and another
  after; the pages that changed are merged into one candidate per key and crawl pair.

Label-tolerant matching: an ``apr`` fact carrying model-year qualifiers is matched by its tier's rank among the
model-year tiers of that product on the same page, newest first, in place of the years, so the calculator's 2023-26
tier and the rate sheet's 2024-27 tier both rank 0. Values are compared by unit and number, so "$100,000" and
"$100,000.00" agree.

Rubric:

- ``high``: an in-force pair across a ``rate_sheet`` or ``product_page`` and a page of authority 1 or less with an
  older effective date, both values unit-bearing (their text shows ``%`` or ``$``);
- ``medium``: an in-force pair between two authority-3 pages, or a cross-crawl change on ``/rates`` or
  ``/business-rates``;
- ``low``: everything else.

Prints one line per candidate, high first; ``--out`` also writes the list as JSON. Offline only: nothing in
``submission/`` imports this file. The store is built the way the graded path builds it (``solution.build()``, then
``ingest`` per crawl from ``snapshots/``), with ingestion's own lines sent to stderr.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections import Counter
from itertools import combinations, permutations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

_MODEL_YEARS = ("model_year_max", "model_year_min")
_TIER = "model_year_rank"  # the qualifier that stands in for the two model years in a match key
_TOP_TYPES = frozenset({"rate_sheet", "product_page"})
_RATE_SHEETS = frozenset({"/rates", "/business-rates"})
_RUBRICS = ("high", "medium", "low")
_KINDS = ("in_force", "cross_crawl")
_UNIT_RE = re.compile(r"[%$]")

MatchKey = Tuple[str, str, Tuple[Tuple[str, Any], ...]]
ValueId = Tuple[str, float]


def _path(fact: Any) -> str:
    """The canonical page path a fact is cited by: a legacy alias shares its canonical page's path."""
    return urlsplit(fact.source.canonical_url).path or "/"


def _years(fact: Any) -> Optional[Tuple[Optional[int], Optional[int]]]:
    """``(model_year_max, model_year_min)`` of an ``apr`` fact that carries either; ``None`` for any other fact."""
    quals = dict(fact.qualifiers)
    if fact.attribute != "apr" or not any(name in quals for name in _MODEL_YEARS):
        return None
    return quals.get("model_year_max"), quals.get("model_year_min")


def _newest_tier_first(tier: Tuple[Optional[int], Optional[int]]) -> Tuple[bool, int, bool, int]:
    """Sort key: the latest model year first, then the latest first year; an open (missing) bound counts as newest."""
    high, low = tier
    return (high is not None, -(high or 0), low is not None, -(low or 0))


def _tier_ranks(facts: Sequence[Any]) -> Dict[Tuple[str, str], Dict[Tuple[Optional[int], Optional[int]], int]]:
    """``(page url, product_id)`` to each model-year tier's rank on that page, 0 for the newest."""
    tiers: Dict[Tuple[str, str], set] = {}
    for fact in facts:
        years = _years(fact)
        if years is not None:
            tiers.setdefault((fact.source.url, fact.product_id), set()).add(years)
    return {page: {tier: rank for rank, tier in enumerate(sorted(found, key=_newest_tier_first))}
            for page, found in tiers.items()}


def _match_key(fact: Any, ranks: Dict[Tuple[str, str], Dict[Tuple[Optional[int], Optional[int]], int]]) -> MatchKey:
    """The fact's key with its model years replaced by their tier rank on the fact's page (any other key as it is)."""
    years = _years(fact)
    if years is None:
        return fact.key
    quals = {name: value for name, value in fact.qualifiers if name not in _MODEL_YEARS}
    quals[_TIER] = ranks[(fact.source.url, fact.product_id)][years]
    return (fact.product_id, fact.attribute, tuple(sorted(quals.items(), key=lambda pair: pair[0])))


def _value_id(fact: Any) -> ValueId:
    return (fact.unit, round(float(fact.value), 4))


def _crawl_facts(store: Any, snapshot_id: str) -> Dict[MatchKey, List[Any]]:
    """One crawl's facts that carry a number, by match key."""
    facts = [f for fs in store.by_key.get(snapshot_id, {}).values() for f in fs if f.value is not None]
    ranks = _tier_ranks(facts)
    out: Dict[MatchKey, List[Any]] = {}
    for fact in facts:
        out.setdefault(_match_key(fact, ranks), []).append(fact)
    return out


def _by_value(facts: Sequence[Any]) -> Dict[ValueId, List[Any]]:
    out: Dict[ValueId, List[Any]] = {}
    for fact in facts:
        out.setdefault(_value_id(fact), []).append(fact)
    return out


def _unit_bearing(group: Sequence[Any]) -> bool:
    return any(_UNIT_RE.search(f.value_text) for f in group)


def _value_entry(group: Sequence[Any]) -> Dict[str, Any]:
    """One value of a candidate: its text (one that shows the unit, else the commonest), pages, types and dates."""
    texts = Counter(f.value_text for f in group)
    text = min(texts, key=lambda t: (_UNIT_RE.search(t) is None, -texts[t], t))
    dates = {f.effective_date for f in group}
    return {
        "value_text": text,
        "pages": sorted({"{}@{}".format(_path(f), f.source.snapshot_id) for f in group}),
        "page_types": sorted({f.source.page_type for f in group}),
        "effective_dates": sorted(dates, key=lambda d: (d is None, d or "")),
    }


def _stale_beside_top(top: Any, low: Any) -> bool:
    """``top`` is on a rate sheet or product page, ``low`` on a page of authority 1 or less with an older date."""
    return (top.source.page_type in _TOP_TYPES and low.source.authority <= 1 and bool(top.effective_date)
            and bool(low.effective_date) and low.effective_date < top.effective_date)


def _in_force_rubric(groups: Sequence[Sequence[Any]]) -> str:
    for a, b in permutations(groups, 2):
        if _unit_bearing(a) and _unit_bearing(b) and any(_stale_beside_top(x, y) for x in a for y in b):
            return "high"
    for a, b in combinations(groups, 2):
        if any(x.source.authority == 3 and y.source.authority == 3 and _path(x) != _path(y) for x in a for y in b):
            return "medium"
    return "low"


def _candidate(kind: str, crawl: str, to_crawl: Optional[str], key: MatchKey,
               values: Dict[ValueId, List[Any]], rubric: str) -> Dict[str, Any]:
    return {"kind": kind, "crawl": crawl, "to_crawl": to_crawl, "key": repr(key),
            "values": [_value_entry(values[v]) for v in sorted(values)], "rubric": rubric}


def _in_force(crawl: str, keyed: Dict[MatchKey, List[Any]]) -> List[Dict[str, Any]]:
    out = []
    for key, facts in keyed.items():
        values = _by_value(facts)
        if len(values) >= 2 and len({_path(f) for f in facts}) >= 2:
            out.append(_candidate("in_force", crawl, None, key, values, _in_force_rubric(list(values.values()))))
    return out


def _cross_crawl(before: str, after: str, old: Dict[MatchKey, List[Any]],
                 new: Dict[MatchKey, List[Any]]) -> List[Dict[str, Any]]:
    """Keys whose single value on a page differs between two consecutive crawls, merged over the changed pages."""
    changed: Dict[MatchKey, Dict[ValueId, List[Any]]] = {}
    rate_sheet: Dict[MatchKey, bool] = {}
    for key in old.keys() & new.keys():
        was = {}
        for fact in old[key]:
            was.setdefault(_path(fact), []).append(fact)
        now = {}
        for fact in new[key]:
            now.setdefault(_path(fact), []).append(fact)
        for page in was.keys() & now.keys():
            a, b = _by_value(was[page]), _by_value(now[page])
            if len(a) == 1 and len(b) == 1 and set(a) != set(b):
                merged = changed.setdefault(key, {})
                for value, facts in list(a.items()) + list(b.items()):
                    merged.setdefault(value, []).extend(facts)
                rate_sheet[key] = rate_sheet.get(key, False) or page in _RATE_SHEETS
    return [_candidate("cross_crawl", before, after, key, values, "medium" if rate_sheet[key] else "low")
            for key, values in changed.items()]


def candidates(store: Any) -> List[Dict[str, Any]]:
    """Every in-force and cross-crawl candidate of a finalised store, high first (see the module docstring).

    Reads ``store.by_key`` and ``store.snapshots()`` only, so the store is left exactly as it was. Order: rubric,
    kind (in-force first), crawl (newest first), then the match key.
    """
    order = [sid for sid, _ in store.snapshots()]
    keyed = {sid: _crawl_facts(store, sid) for sid in order}
    found: List[Dict[str, Any]] = []
    for sid in order:
        found.extend(_in_force(sid, keyed[sid]))
    for before, after in zip(order, order[1:]):
        found.extend(_cross_crawl(before, after, keyed[before], keyed[after]))
    position = {sid: i for i, sid in enumerate(order)}
    found.sort(key=lambda c: (_RUBRICS.index(c["rubric"]), _KINDS.index(c["kind"]), -position[c["crawl"]], c["key"]))
    return found


def _short(snapshot_id: str) -> str:
    return snapshot_id.split("_", 1)[0]


def describe(candidate: Dict[str, Any]) -> str:
    """One printable line: rubric, kind, crawl(s), match key, then each value with its pages."""
    crawls = _short(candidate["crawl"]) + ("->" + _short(candidate["to_crawl"]) if candidate["to_crawl"] else "")
    values = " | ".join("{} [{}]".format(v["value_text"], ", ".join(
        p.split("@")[0] + "@" + _short(p.split("@")[1]) for p in v["pages"])) for v in candidate["values"])
    return "{:<6} {:<11} {:<6} {} :: {}".format(candidate["rubric"], candidate["kind"], crawls, candidate["key"], values)


def load_store(snapshots: Path) -> Any:
    """The finalised store of every crawl under ``snapshots``, built by the facade's own ``ingest``."""
    for folder in ("harness", "submission"):
        if str(ROOT / folder) not in sys.path:
            sys.path.insert(0, str(ROOT / folder))
    import solution  # noqa: E402  (imported here: importing this module stays free of side effects)
    from run_eval import load_snapshots  # noqa: E402

    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(snapshots):
            ks.ingest(snapshot)
    return ks.store


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="List conflict candidates in the five crawls, high first.")
    parser.add_argument("--out", type=Path, default=None, help="also write the candidates here as JSON")
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots", help="the crawl folders (default: snapshots/)")
    args = parser.parse_args(argv)
    found = candidates(load_store(args.snapshots))
    for candidate in found:
        print(describe(candidate))
    counts = Counter(c["rubric"] for c in found)
    print("candidates: {} (high {}, medium {}, low {})".format(len(found), counts["high"], counts["medium"],
                                                                counts["low"]), file=sys.stderr)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
