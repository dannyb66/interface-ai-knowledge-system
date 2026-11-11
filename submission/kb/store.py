"""Fact store: per-snapshot indexes, as_of snapshot selection and the ranking that decides which fact wins."""
from __future__ import annotations

import re
from bisect import bisect_right
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from kb.errors import KBError
from kb.types import Fact, FactKey

_ISO_DAY = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")  # ASCII digits only: \d would accept other scripts
_UNDATED = "0000-00-00"  # a missing date orders as the oldest possible one


class AsOfError(KBError):
    """``as_of`` is not an ISO ``YYYY-MM-DD`` date: carries ``KB-E04``."""

    def __init__(self, value: object = None) -> None:
        super().__init__("KB-E04", value=value)


def _is_iso_day(text: object) -> bool:
    """True for a real calendar date written ``YYYY-MM-DD``, with nothing around it (not even a newline)."""
    if not isinstance(text, str):
        return False
    parsed = _ISO_DAY.fullmatch(text)
    if parsed is None:
        return False
    try:
        date(int(parsed.group(1)), int(parsed.group(2)), int(parsed.group(3)))
    except ValueError:  # 2026-02-30, month 13, year 0000
        return False
    return True


def _check_as_of(as_of: Optional[str]) -> Optional[str]:
    """``None`` stays ``None`` and an ISO ``YYYY-MM-DD`` string passes; anything else raises ``AsOfError``."""
    if as_of is None or _is_iso_day(as_of):
        return as_of
    raise AsOfError(as_of)


def _newest_first(text: Optional[str]) -> Tuple[int, ...]:
    """Sort-key part that makes an ascending sort order strings DESCENDING, exactly, for any two strings.

    Code points are negated. The closing ``1`` sits above every negated code point, so a string that extends
    another (a full timestamp over its bare date) still sorts first, as in a plain descending string sort.
    A missing date (``None`` or empty) is read as ``0000-00-00``, the oldest.
    """
    return tuple(-ord(ch) for ch in (text or _UNDATED)) + (1,)


def rank(f: Fact) -> Tuple:
    """Explicit sort key: sorting ascending puts the winning fact first.

    Highest authority, then newest effective date, newest published date, newest fetch time, then canonical
    URL ascending. ``block_idx`` and ``row_idx`` only break what is left, so insertion order matters only for
    facts equal in all seven parts.
    """
    s = f.source
    return (
        -s.authority,
        _newest_first(f.effective_date),
        _newest_first(f.published_date),
        _newest_first(s.fetched_at),
        s.canonical_url,
        s.block_idx,
        s.row_idx,
    )


class FactStore:
    """Facts grouped by crawl snapshot. ``add`` stores them, ``finalize`` indexes them, ``in_force`` reads them.

    ``by_key`` and ``by_product_attr`` map a snapshot id to that snapshot's index: a fact key, or a
    ``(product_id, attribute)`` pair, to its facts with the best ``rank`` first. They are fresh only after
    ``finalize()``. ``in_force`` never builds them: it raises ``RuntimeError`` when facts were added since the
    last ``finalize()``, so answering a question can never trigger an index build.
    """

    def __init__(self) -> None:
        self._taken_on: Dict[str, str] = {}
        self._raw: Dict[str, List[Fact]] = {}  # every fact added, per snapshot, in insertion order
        self._dirty = False
        self.by_key: Dict[str, Dict[FactKey, List[Fact]]] = {}
        self.by_product_attr: Dict[str, Dict[Tuple[str, str], List[Fact]]] = {}

    def add(self, snapshot_id: str, taken_on: str, facts: Iterable[Fact]) -> None:
        """Register a snapshot (even one without facts) and append its facts; call again to add more to it.

        Atomic: the facts are read in full before any state changes, so a bad ``taken_on`` or an iterable that
        raises midway leaves the store exactly as it was. The indexes stay stale until the next ``finalize()``.
        """
        if not _is_iso_day(taken_on):
            raise ValueError("taken_on must be an ISO date (YYYY-MM-DD), got {!r}".format(taken_on))
        known = self._taken_on.get(snapshot_id)
        if known is not None and known != taken_on:
            raise ValueError("snapshot {!r} was added with taken_on {}, now {}".format(snapshot_id, known, taken_on))
        batch = list(facts)  # may raise: nothing has changed yet
        self._taken_on[snapshot_id] = taken_on
        self._raw.setdefault(snapshot_id, []).extend(batch)
        self._dirty = True

    def finalize(self) -> None:
        """Rebuild every index from the facts added so far, each list best ``rank`` first; safe to repeat."""
        by_key: Dict[str, Dict[FactKey, List[Fact]]] = {}
        by_product_attr: Dict[str, Dict[Tuple[str, str], List[Fact]]] = {}
        for snapshot_id, facts in self._raw.items():  # all registered snapshots, empty ones included
            keyed: Dict[FactKey, List[Fact]] = {}
            paired: Dict[Tuple[str, str], List[Fact]] = {}
            for f in sorted(facts, key=rank):  # one sort keeps every sub-list in rank order
                keyed.setdefault(f.key, []).append(f)
                paired.setdefault((f.product_id, f.attribute), []).append(f)
            by_key[snapshot_id] = keyed
            by_product_attr[snapshot_id] = paired
        self.by_key = by_key
        self.by_product_attr = by_product_attr
        self._dirty = False

    def snapshots(self) -> List[Tuple[str, str]]:
        """``(snapshot_id, taken_on)`` pairs, oldest crawl first (the id breaks a same-day tie)."""
        return sorted(self._taken_on.items(), key=lambda pair: (pair[1], pair[0]))

    def snapshot_for(self, as_of: Optional[str]) -> Tuple[str, str]:
        """``(snapshot_id, note)``: the newest crawl taken on or before ``as_of``, note ``""``.

        ``None``, or a date after the last crawl, gives the latest snapshot. A date before the first crawl gives
        the earliest snapshot with note ``"earliest crawl"``. ``as_of`` must be ``None`` or ``YYYY-MM-DD``,
        else ``AsOfError``; the canonicaliser normalises other formats before this is called.
        """
        day = _check_as_of(as_of)
        order = self.snapshots()
        if not order:
            raise LookupError("FactStore has no snapshots: add() one before snapshot_for()")
        if day is None:
            return order[-1][0], ""
        pos = bisect_right([taken_on for _, taken_on in order], day) - 1  # last crawl taken on or before day
        if pos < 0:
            return order[0][0], "earliest crawl"
        return order[pos][0], ""

    def in_force(self, snapshot_id: str, product_id: str, attribute: str, as_of: Optional[str]) -> List[Fact]:
        """Facts for ``(product_id, attribute)`` in one snapshot, best ``rank`` first, as a new list.

        With ``as_of`` set, a fact whose ``effective_date`` is later than it is left out; a fact with no
        effective date is never left out. Raises ``AsOfError`` for a bad ``as_of``, ``RuntimeError`` when facts
        were added since the last ``finalize()`` (it never builds the indexes itself) and ``KeyError`` for a
        snapshot id that was never added.
        """
        day = _check_as_of(as_of)
        if self._dirty:
            raise RuntimeError("store not finalised: call finalize() after add()")
        if snapshot_id not in self.by_product_attr:
            raise KeyError("unknown snapshot {!r}".format(snapshot_id))
        facts = self.by_product_attr[snapshot_id].get((product_id, attribute), [])
        if day is None:
            return list(facts)
        return [f for f in facts if not f.effective_date or f.effective_date <= day]
