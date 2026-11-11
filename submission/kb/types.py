"""Frozen data contracts every kb module imports: facts, their sources, answer plans and curated conflicts.

Qualifier values are JSON scalars (str, int, float, bool): ``make_key`` drops ``None``, and a tuple-valued
qualifier would not survive ``fact_to_dict`` / ``fact_from_dict`` (JSON turns it into an unhashable list).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

# (product_id, attribute, qualifiers): the qualifiers are (name, value) pairs sorted by name, ``None`` dropped.
FactKey = Tuple[str, str, Tuple[Tuple[str, Any], ...]]


class ClaimType(Enum):
    """The kind of claim a fact makes; the resolver selects per kind."""

    RATE = "rate"
    STATUS = "status"
    ASSERTION = "assertion"


@dataclass(frozen=True)
class Source:
    """Where a fact was read: the page, its crawl snapshot and the exact row or sentence."""

    url: str
    canonical_url: str
    page_type: str
    authority: int  # authority class from data/authority.json
    snapshot_id: str
    fetched_at: str
    block_idx: int  # position of the quote: block on the page ...
    row_idx: int  # ... and row within that block
    quote: str  # the raw table row or sentence, footnotes and all


@dataclass(frozen=True)
class Fact:
    """One value for one (product, attribute, qualifiers) key, with its provenance."""

    key: FactKey
    product_id: str
    attribute: str
    qualifiers: Tuple[Tuple[str, Any], ...]
    value: Optional[float]
    value_text: str  # the cell after footnote stripping: "4.10%2" becomes "4.10%"
    unit: str
    claim_type: ClaimType
    effective_date: Optional[str]
    event_date: Optional[str]
    published_date: Optional[str]
    source: Source
    extractor: str
    confidence: float


@dataclass(frozen=True)
class AnswerPlan:
    """The only input to the composer and the lint."""

    intent: str
    facts: Tuple[Fact, ...]
    permitted_values: FrozenSet[Tuple[str, float]]  # (unit, number) pairs the rendered text may contain
    sources: Tuple[Source, ...]
    confident: bool  # False only for refusal plans
    conflict_note: Optional[str]
    snapshot_id: Optional[str]
    refusal_span: Optional[str] = None  # what the refusal says Dupaco's website does not list
    as_of: Optional[str] = None  # the ISO date the question or the argument supplied; None when neither did
    question: Optional[str] = None  # the question as parsed (``Query.raw_span``: cut, stripped, digits kept)
    first_crawl: Optional[str] = None  # ``taken_on`` of the earliest ingested crawl (``resolve`` sets it)
    crawl_date: Optional[str] = None  # ``taken_on`` of the answering crawl, ``snapshot_id``'s; None without one
    strict_numbers: bool = False  # a prose or curated fact is in the plan: the lint checks bare numbers too
    as_of_end: Optional[str] = None
    withdrawn: bool = False
    same_crawl: bool = False


@dataclass(frozen=True)
class CuratedSource:
    """One source of a curated conflict: the page, its crawl, the value it shows and the quote that shows it."""

    url: str
    snapshot_id: str
    value: str  # one of the entry's values, found inside ``quote``
    quote: str  # copied from the page text of that crawl


@dataclass(frozen=True)
class CuratedConflict:
    """The in-memory and on-disk shape of one entry of data/conflicts_curated.json."""

    topic: str
    values: Tuple[str, ...]
    sources: Tuple[CuratedSource, ...]
    resolution: str
    reason: str
    confidence: float
    keys: Tuple[Tuple[str, str], ...] = ()  # the (product_id, attribute) pairs whose answers note this conflict


def make_key(product_id: str, attribute: str, qualifiers: Mapping[str, Any]) -> FactKey:
    """The canonical key: qualifiers sorted by name, ``None`` values dropped (``False`` and ``0`` stay)."""
    pairs = sorted(((name, value) for name, value in qualifiers.items() if value is not None), key=lambda pair: pair[0])
    return (product_id, attribute, tuple(pairs))


def _pairs_to_lists(pairs: Iterable[Sequence[Any]]) -> List[List[Any]]:
    return [list(pair) for pair in pairs]


def _pairs_from_lists(pairs: Iterable[Sequence[Any]]) -> Tuple[Tuple[str, Any], ...]:
    return tuple((name, value) for name, value in pairs)


def fact_to_dict(f: Fact) -> dict:
    """A JSON-ready dict: the enum as its value, tuples as lists, ``source`` as a nested dict."""
    return {
        "key": [f.key[0], f.key[1], _pairs_to_lists(f.key[2])],
        "product_id": f.product_id,
        "attribute": f.attribute,
        "qualifiers": _pairs_to_lists(f.qualifiers),
        "value": f.value,
        "value_text": f.value_text,
        "unit": f.unit,
        "claim_type": f.claim_type.value,
        "effective_date": f.effective_date,
        "event_date": f.event_date,
        "published_date": f.published_date,
        "source": asdict(f.source),
        "extractor": f.extractor,
        "confidence": f.confidence,
    }


def fact_from_dict(d: dict) -> Fact:
    """The inverse of ``fact_to_dict``: rebuilds the tuples, the enum and the nested ``Source``.

    The stored ``key`` is restored as written, not recomputed, so any ``Fact`` round-trips exactly.
    """
    key = d["key"]
    return Fact(
        key=(key[0], key[1], _pairs_from_lists(key[2])),
        product_id=d["product_id"],
        attribute=d["attribute"],
        qualifiers=_pairs_from_lists(d["qualifiers"]),
        value=d["value"],
        value_text=d["value_text"],
        unit=d["unit"],
        claim_type=ClaimType(d["claim_type"]),
        effective_date=d["effective_date"],
        event_date=d["event_date"],
        published_date=d["published_date"],
        source=Source(**d["source"]),
        extractor=d["extractor"],
        confidence=d["confidence"],
    )
