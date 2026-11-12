"""Optional evidence emitted by the real parser and arbitration steps.

These records explain decisions; they are neither independent truth labels nor
permission to recover a refusal. No trace is built on the normal answer path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence

from .types import AnswerPlan, Fact, fact_to_dict


class Origin(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    DEFAULT = "default"
    ABSENT = "absent"


class RefusalReason(str, Enum):
    MALFORMED_DATE = "malformed_date"
    UNKNOWN_ENTITY = "unknown_entity"
    UNPUBLISHED_ATTRIBUTE = "unpublished_attribute"
    UNAVAILABLE_SEGMENT = "unavailable_segment"
    UNAVAILABLE_PROGRAM = "unavailable_program"
    NO_ELIGIBLE_CRAWL = "no_eligible_crawl"
    UNLISTED_BRANCH = "unlisted_branch"
    UNAVAILABLE_QUALIFIER = "unavailable_qualifier"
    NO_ELIGIBLE_FACT = "no_eligible_fact"
    WITHDRAWN = "withdrawn"
    AMBIGUOUS = "ambiguous"
    RENDERING_GROUNDING = "rendering_grounding"
    INCOMPLETE_CLAIM_GROUP = "incomplete_claim_group"


def fact_id(fact: Fact) -> str:
    encoded = json.dumps(fact_to_dict(fact), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


@dataclass
class ResolutionTrace:
    """A fresh trace belongs to one uncached explanation, never the answer cache."""
    parser: Dict[str, Any] = field(default_factory=dict)
    steps: List[dict] = field(default_factory=list)
    candidates: Dict[str, dict] = field(default_factory=dict)
    refusals: List[dict] = field(default_factory=list)

    def field(self, name: str, value: Any, origin: Origin, evidence: Any = None) -> None:
        self.parser[name] = {"value": value, "origin": origin.value, "evidence": evidence}

    def pool(self, stage: str, before: Sequence[Fact], after: Sequence[Fact], **details: Any) -> None:
        before_ids, after_ids = [], []
        for facts, ids in ((before, before_ids), (after, after_ids)):
            for fact in facts:
                identity = fact_id(fact)
                ids.append(identity)
                self.candidates.setdefault(identity, fact_to_dict(fact))
        kept = set(after_ids)
        self.steps.append({"stage": stage, "input_ids": before_ids, "kept_ids": after_ids,
                           "rejected_ids": [identity for identity in before_ids if identity not in kept],
                           "input_count": len(before_ids), "kept_count": len(after_ids), **details})

    def reject(self, reason: RefusalReason, product_id: Optional[str] = None, **details: Any) -> None:
        self.refusals.append({"reason": reason.value, "product_id": product_id, **details})

    def finish(self, plan: AnswerPlan, answer: Any, dropped: Sequence[str]) -> None:
        if plan.confident and not answer.confident:
            self.reject(RefusalReason.RENDERING_GROUNDING)
        self.pool("render", plan.facts, plan.facts if answer.confident else (),
                  confident=answer.confident, dropped_sentences=list(dropped))

    def to_dict(self) -> dict:
        return {"version": 1, "parser": self.parser, "steps": self.steps,
                "candidate_facts": self.candidates, "refusals": self.refusals}


def capture_parse(trace: ResolutionTrace, q: Any, hits: Sequence[Any], attrs: Any,
                  keyword: str, requirement: Optional[str], tokens: Sequence[str], as_of: Any) -> None:
    """Use evidence computed by parse(), rather than reparsing or guessing from its final result."""
    explicit_products = [target for _, _, (kind, target) in hits if kind == "product"]
    entity_origin = (Origin.ABSENT if q.product_id is None else Origin.EXPLICIT
                     if q.product_id in explicit_products else Origin.INFERRED)
    trace.field("entity", q.product_id, entity_origin, explicit_products)
    attr_origin = Origin.ABSENT if q.attribute is None else (
        Origin.EXPLICIT if attrs or requirement else Origin.INFERRED if keyword else Origin.DEFAULT)
    trace.field("attribute", q.attribute, attr_origin, sorted(attrs) or requirement or keyword or None)
    origin = Origin.DEFAULT if q.intent == "value" and not keyword else Origin.EXPLICIT
    if q.intent == "list" and not set(tokens) & {"all", "list", "which", "what", "types", "kinds"}:
        origin = Origin.INFERRED
    trace.field("intent", q.intent, origin, keyword or (tokens[0] if tokens else None))
    trace.field("as_of", q.as_of, Origin.EXPLICIT if as_of is not None or q.as_of is not None else Origin.DEFAULT,
                "argument" if as_of is not None else "question" if q.as_of is not None else "latest crawl")
    qualifiers = {}
    words = set(tokens)
    for name, value in q.slots:
        origin = Origin.EXPLICIT
        if name == "segment" and not words & {"personal", "business", "businesses", "commercial"}:
            origin = Origin.DEFAULT
        elif name == "program" and value in ("purchase", "refi") and not words & {"purchase", "refinance", "refi"}:
            origin = Origin.INFERRED
        elif name == "special" and not words & {"special", "specials", "regular"}:
            origin = Origin.INFERRED
        qualifiers[name] = {"value": value, "origin": origin.value}
    trace.parser["qualifiers"] = qualifiers
    trace.parser["original_question"] = q.raw_span
    trace.parser["question_numbers"] = [list(number) for number in sorted(q.question_numbers)]
    trace.field("requested_prose_attributes", list(q.requested_prose_attributes),
                Origin.EXPLICIT if q.requested_prose_attributes else Origin.ABSENT)


def answer_dict(answer: Any) -> dict:
    return {"text": answer.text, "confident": answer.confident, "conflict_note": answer.conflict_note,
            "sources": [asdict(source) for source in answer.sources]}


def diagnosed(plan: AnswerPlan, trace: Optional[ResolutionTrace], reason: RefusalReason,
              product_id: Optional[str] = None) -> AnswerPlan:
    if trace is not None and not plan.confident:
        trace.reject(RefusalReason.WITHDRAWN if plan.withdrawn else reason, product_id)
    return plan
