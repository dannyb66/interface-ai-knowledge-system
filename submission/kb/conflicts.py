"""Curated conflicts: parse ``data/conflicts_curated.json``, verify each source at ingest, emit the survivors.

The file is ``{"_version": ..., "conflicts": [entry, ...]}``. An entry has ``topic``, ``values``, ``sources`` (each
``url``, ``snapshot_id``, ``value``, ``quote``), ``resolution``, ``reason``, ``confidence`` and optionally ``keys``
(``[product_id, attribute]`` pairs). ``parse_curated`` rejects a malformed entry with a ``ValueError`` naming its
topic: every value must be unit-bearing and have a source, every source value must be one of the values, the
resolution's numbers must come from the values, the confidence must lie in [0, 1] and topics must be unique.

``ConflictBook.observe`` runs once per crawl at ingest with the pages that crawl's sources need (canonical URL to
markdown). A source verifies when its quote is on its page (``verify.quote_found`` on ``verify.page_text``) and its
value lies inside its quote (``verify.value_in_quote``). The result is stored per source, so the order in which
crawls arrive does not matter. ``emit`` only reads the stored results: an entry is emitted when every source
verified (every value has a source, so every value is verified too), confidence first, ties in file order, as fresh
``contract.Conflict`` objects. ``dropped`` names the entries whose crawls were all observed and that still failed.

Answer notes: ``note_index`` maps each ``(product_id, attribute)`` an entry lists in ``keys`` to the verified entries,
in ``emit`` order. ``with_note`` gives a confident answer whose plan's first fact is under such a key the note of the
first entry whose resolution shares a number with that fact's ``value_text``: "Sources disagree (<values>);
<resolution> is current. <reason>", joined onto ``conflict_note``. The answer's text never changes, and a failure
in the note step keeps the answer without a note.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple

from contract import Answer, Conflict
from contract import Source as ContractSource

from .normalize import canonical_url, number_tokens
from .plans import join_notes
from .types import AnswerPlan, CuratedConflict, CuratedSource, Fact
from .verify import page_text, quote_found, unit_bearing, value_in_quote
from .source_pages import SourcePages, matching, variants

_FIELDS = ("topic", "values", "sources", "resolution", "reason", "confidence")
_SOURCE_FIELDS = ("url", "snapshot_id", "value", "quote")

NoteIndex = Dict[Tuple[str, str], List[CuratedConflict]]


def _texts(row: Mapping[str, Any], fields: Iterable[str], fail: Callable[[str], ValueError]) -> List[str]:
    out = []
    for field in fields:
        value = row[field]
        if not isinstance(value, str) or not value.strip():
            raise fail("{} must be non-empty text".format(field))
        out.append(value)
    return out


def _source(raw: Any, fail: Callable[[str], ValueError]) -> CuratedSource:
    if not isinstance(raw, Mapping):
        raise fail("a source is not an object")
    missing = [field for field in _SOURCE_FIELDS if field not in raw]
    if missing:
        raise fail("a source is missing field " + ", ".join(missing))
    url, snapshot_id, value, quote = _texts(raw, _SOURCE_FIELDS, fail)
    return CuratedSource(url, snapshot_id, value, quote)


def _keys(raw: Any, fail: Callable[[str], ValueError]) -> Tuple[Tuple[str, str], ...]:
    pairs = raw if isinstance(raw, list) else None
    if pairs is None or not all(isinstance(pair, list) and len(pair) == 2
                                and all(isinstance(part, str) and part for part in pair) for pair in pairs):
        raise fail("keys must be a list of [product_id, attribute] pairs")
    return tuple((pair[0], pair[1]) for pair in pairs)


def _entry(row: Any, number: int) -> CuratedConflict:
    """One checked entry; ``number`` (from 1) names it when it has no usable topic."""
    named = row.get("topic") if isinstance(row, Mapping) else None
    name = named if isinstance(named, str) and named.strip() else "#{}".format(number)

    def fail(why: str) -> ValueError:
        return ValueError("curated conflict {!r}: {}".format(name, why))

    if not isinstance(row, Mapping):
        raise fail("not an object")
    missing = [field for field in _FIELDS if field not in row]
    if missing:
        raise fail("missing field " + ", ".join(missing))
    topic, resolution, reason = _texts(row, ("topic", "resolution", "reason"), fail)
    values = row["values"]
    if not isinstance(values, list) or len(values) < 2 or not all(isinstance(v, str) and v.strip() for v in values):
        raise fail("values must be a list of at least two non-empty strings")
    if len(set(values)) != len(values):
        raise fail("a value is listed twice")
    for value in values:
        if not unit_bearing(value):
            raise fail("value {!r} is not unit-bearing (no %, $, or number or ordinal word before a word)".format(
                value))
    if not isinstance(row["sources"], list) or not row["sources"]:
        raise fail("sources must be a non-empty list")
    sources = tuple(_source(raw, fail) for raw in row["sources"])
    for source in sources:
        if source.value not in values:
            raise fail("source value {!r} is not one of the values".format(source.value))
    for value in values:
        if not any(source.value == value for source in sources):
            raise fail("value {!r} has no source".format(value))
    allowed: Set[Tuple[str, float]] = set().union(*(number_tokens(value) for value in values))
    if not number_tokens(resolution) <= allowed:
        raise fail("resolution {!r} has a number that is not in the values".format(resolution))
    confidence = row["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        raise fail("confidence must be a number in [0, 1]")
    keys = _keys(row.get("keys", []), fail)
    return CuratedConflict(topic, tuple(values), sources, resolution, reason, float(confidence), keys)


def parse_curated(data: Mapping[str, Any]) -> List[CuratedConflict]:
    """The checked entries in file order; ``ValueError`` naming the topic for the first bad one (module docstring)."""
    rows = data.get("conflicts") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("curated conflicts: the file needs a 'conflicts' list")
    out: List[CuratedConflict] = []
    seen: Set[str] = set()
    for number, row in enumerate(rows, 1):
        entry = _entry(row, number)
        folded = " ".join(entry.topic.lower().split())  # the scorer compares topics this way
        if folded in seen:
            raise ValueError("curated conflict {!r}: duplicate topic".format(entry.topic))
        seen.add(folded)
        out.append(entry)
    return out


def load_curated(path: Path) -> List[CuratedConflict]:
    """``parse_curated`` of a JSON file; ``OSError`` or ``ValueError`` when it is missing or invalid."""
    with open(path, encoding="utf-8") as fh:
        return parse_curated(json.load(fh))


def _conflict(entry: CuratedConflict) -> Conflict:
    sources = [ContractSource(url=s.url, snapshot_id=s.snapshot_id, quote=s.quote) for s in entry.sources]
    return Conflict(topic=entry.topic, values=list(entry.values), sources=sources, resolution=entry.resolution,
                    reason=entry.reason)


class ConflictBook:
    """The curated entries and, per source, the result of its check at ingest (``None`` when it verified)."""

    def __init__(self, entries: Iterable[CuratedConflict]) -> None:
        self._entries: Tuple[CuratedConflict, ...] = tuple(entries)
        self._checks: Dict[Tuple[int, int], Optional[str]] = {}
        self._resolved: Dict[Tuple[int, int], CuratedSource] = {}
        needed: Dict[str, Set[str]] = {}
        for entry in self._entries:
            for source in entry.sources:
                needed.setdefault(source.snapshot_id, set()).add(canonical_url(source.url))
        self._needed = {snapshot_id: frozenset(urls) for snapshot_id, urls in needed.items()}

    def pages_needed(self, snapshot_id: str) -> FrozenSet[str]:
        """The canonical URLs this crawl's sources name."""
        return self._needed.get(snapshot_id, frozenset())

    def observe(self, snapshot_id: str, pages: Mapping[str, str], normalized=None) -> None:
        """Check every source of this crawl against ``pages`` (canonical URL to markdown) and store the results."""
        texts: Dict[str, str] = {} if normalized is None else normalized
        for i, entry in enumerate(self._entries):
            for j, source in enumerate(entry.sources):
                if source.snapshot_id == snapshot_id:
                    why, matched = _check_match(source, pages, texts)
                    self._checks[(i, j)] = why
                    if matched is not None:
                        self._resolved[(i, j)] = dataclasses.replace(source, url=matched.raw_url) if isinstance(pages, SourcePages) else source

    def _failure(self, i: int) -> Optional[str]:
        """``None`` when every source of entry ``i`` verified, else why the first one did not."""
        for j, source in enumerate(self._entries[i].sources):
            if (i, j) not in self._checks:
                return "crawl {} was not checked".format(source.snapshot_id)
            why = self._checks[(i, j)]
            if why is not None:
                return why
        return None

    def verified(self) -> List[CuratedConflict]:
        """The entries every source of which verified, confidence first, ties in file order."""
        order = sorted(range(len(self._entries)), key=lambda i: (-self._entries[i].confidence, i))
        return [dataclasses.replace(self._entries[i], sources=tuple(self._resolved.get((i, j), source)
                for j, source in enumerate(self._entries[i].sources))) for i in order if self._failure(i) is None]

    def emit(self) -> List[Conflict]:
        """Fresh ``contract.Conflict`` objects for the verified entries, in ``verified`` order."""
        return [_conflict(entry) for entry in self.verified()]

    def dropped(self, observed: Iterable[str]) -> List[Tuple[str, str]]:
        """``(topic, why)`` in file order for each entry whose crawls are all in ``observed`` and that failed."""
        seen = set(observed)
        out = []
        for i, entry in enumerate(self._entries):
            if {source.snapshot_id for source in entry.sources} <= seen:
                why = self._failure(i)
                if why is not None:
                    out.append((entry.topic, why))
        return out


def _check(source: CuratedSource, pages: Mapping[str, str], texts: Dict[str, str]) -> Optional[str]:
    """``None`` when the source verifies, else why not; ``texts`` caches each page's ``page_text``."""
    return _check_match(source, pages, texts)[0]


def _check_match(source, pages, texts):
    url = canonical_url(source.url)
    found = matching(pages, source.url, source.snapshot_id, source.quote, texts, page_text, exact_raw=True)
    if not found:
        why = "page missing" if not variants(pages, url, source.snapshot_id) else "quote/source identity missing or ambiguous"
        return "{} on {} in crawl {}".format(why, url, source.snapshot_id), None
    if not value_in_quote(source.value, source.quote):
        return "the value {} is not inside its quote on {} in crawl {}".format(source.value, url, source.snapshot_id), None
    return None, found[0]


def note_index(entries: Iterable[CuratedConflict]) -> NoteIndex:
    """``(product_id, attribute)`` to the entries that list it in ``keys``, in the order given."""
    index: NoteIndex = {}
    for entry in entries:
        for key in entry.keys:
            index.setdefault(key, []).append(entry)
    return index


def answer_note(index: NoteIndex, fact: Fact) -> Optional[str]:
    """The note of the first entry under the fact's ``(product_id, attribute)`` whose resolution shares a number
    (unit included) with the fact's ``value_text``; ``None`` when no entry does."""
    shown = number_tokens(fact.value_text)
    for entry in index.get((fact.product_id, fact.attribute), ()):
        if number_tokens(entry.resolution) & shown:
            return "Sources disagree ({}); {} is current. {}".format(", ".join(entry.values), entry.resolution,
                                                                     entry.reason)
    return None


def with_note(answer: Answer, plan: AnswerPlan, index: NoteIndex) -> Answer:
    """``answer`` with the curated note of the plan's first fact joined onto its ``conflict_note``, when the plan and
    the answer are both confident and the fact has one; otherwise ``answer`` itself. The text never changes, and a
    failure while finding the note also returns ``answer`` itself, never a refusal."""
    try:
        if not (plan.confident and answer.confident and plan.facts):
            return answer
        note = answer_note(index, plan.facts[0])
        if note is None:
            return answer
        return dataclasses.replace(answer, conflict_note=join_notes(answer.conflict_note, note))
    except Exception:  # the note is extra: its failure must not cost the member the answer
        return answer
