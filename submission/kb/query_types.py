"""Immutable parsed question metadata, re-exported by kb.question."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class Query:
    """What a question asks (intent, product, attribute, slots) and for which date."""

    intent: str
    product_id: Optional[str]
    attribute: Optional[str]
    slots: Tuple[Tuple[str, Any], ...]  # (name, value) pairs sorted by name
    as_of: Optional[str]
    as_of_error: bool
    raw_span: str  # the cut question, stripped: the only text a refusal may quote
    question_numbers: FrozenSet[Tuple[str, float]]
    canonical_key: str
    product_ids: Tuple[str, ...] = ()  # product_id, then the other products asked in question order; () when none
    # Explicit past-value wording ("the previous rate", "what it paid before it changed"): the value before the latest
    # change. Never on a bare "was" and never on a ``change`` question, whose template shows both sides already.
    past: bool = False
    as_of_end: Optional[str] = None
    change_point: bool = False
    mentions: Tuple[Tuple[Tuple[str, Any], ...], ...] = ()
    generic_rate: bool = False
    families: Tuple[str, ...] = ()
    explicit_attribute: bool = False
    explicit_entity: bool = False
    route_blocked: bool = False
    requested_prose_attributes: Tuple[str, ...] = ()
    prose_scope_error: bool = False
    serving_as_of: Optional[str] = None  # caller cutoff independent of comparison endpoints
    prose_reinterpreted: bool = False  # contextual predicate repair; original numbers and wording are retained
