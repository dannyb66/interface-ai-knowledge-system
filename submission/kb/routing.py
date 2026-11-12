"""Allowlisted query transitions; the normal resolver retains sole fact arbitration."""
from __future__ import annotations

from dataclasses import replace
import re

from .conditions import query_conditions
from .diagnostics import Origin
from .lexical_index import tokens

_HARD_SLOTS = frozenset({"program", "jumbo", "special", "term_months", "amount", "model_year", "model_year_range",
                         "latest_model_year", "branch_name", "day", "intro", "year", "year_back", "superlative"})
_UNKNOWN_BLOCK = re.compile(r"\b(?:not|never|without|except|instead|guaranteed|personally|exact|my|our)\b", re.I)
_INFORMATION = re.compile(r"\b(?:purpose|explain|describe|description|designed|intended|steps|process|procedure|goals)\b|"
                          r"\bhow\b.*\b(?:work|works|help|helps)\b", re.I)
_RATE_ATTRIBUTES = frozenset({"apr", "apy", "rate", "dividend_rate"})


def recoverable_attribute(query):
    return (query.attribute is None or not query.explicit_attribute and query.attribute in _RATE_ATTRIBUTES
            and bool(_INFORMATION.search(query.raw_span)))


def eligible(query, config, index=None):
    current_date = query.as_of is None or index is not None and query.as_of == index.latest_day
    preserve_attribute = query.product_id is None and query.attribute in ("description", "eligibility", "fee")
    if (not config.lexical_routing or query.as_of_error or query.route_blocked or query.prose_scope_error
            or query.explicit_attribute and not preserve_attribute
            or not current_date or query.past or query.as_of_end or query.change_point or query.mentions
            or query.question_numbers or query.requested_prose_attributes
            or len(query.product_ids) > 1 or query.families or query.intent not in ("value", "how_to")
            or any(key in _HARD_SLOTS for key, _ in query.slots)):
        return False
    if query.product_id is not None:
        return recoverable_attribute(query)
    return bool(config.unknown_topic_routing and query.attribute in (None, "description", "eligibility", "fee")
                and not _UNKNOWN_BLOCK.search(query.raw_span)
                and dict(query.slots).get("segment") != "business")


def apply_route(query, route, latest_day=None):
    """Preserve source wording, numbers and explicit slots; never reparse synthetic text."""
    current_date = query.as_of is None or latest_day is not None and query.as_of == latest_day
    same_attribute = query.attribute is not None and query.attribute == route.attribute
    if (query.as_of_error or query.prose_scope_error or not current_date or query.past or query.as_of_end or query.change_point
            or query.mentions or query.families or query.requested_prose_attributes or len(query.product_ids) > 1
            or query.explicit_attribute and not same_attribute
            or not same_attribute and not recoverable_attribute(query)
            or query.product_id not in (None, route.product_id)):
        raise ValueError("route would override explicit or unsupported query semantics")
    slots = dict(query.slots)
    if route.attribute == "fee":
        slots.update(query_conditions(query.raw_span))
    slots = tuple(sorted(slots.items()))
    key = "{}|{}|{}|{}|{}".format(query.intent, route.product_id, route.attribute, list(slots), query.as_of)
    return replace(query, product_id=route.product_id, product_ids=(route.product_id,), attribute=route.attribute,
                   slots=slots, canonical_key=key, generic_rate=False, families=(), mentions=())


def recover(query, index, registry, config, trace=None):
    if not eligible(query, config, index):
        return query
    requested = query.attribute if query.explicit_attribute else None
    ranked = index.rank(query.raw_span, query.product_id, requested)
    if query.product_id is None:
        ranked = [route for route in ranked if registry.family(route.product_id) == "information"
                  and route.attribute in ("description", "eligibility")]
    reason = "no compatible source-derived target"
    chosen = None
    if ranked:
        first, second = ranked[0], ranked[1].score if len(ranked) > 1 else 0.0
        # Two anchor words protect unknown-topic discovery; no nearest-result default.
        anchors = 2 if query.product_id is None else 0
        if first.score >= config.routing_min_score and first.score - second >= config.routing_min_margin:
            if first.anchor_matches >= anchors and first.token_matches >= 2:
                chosen = first
        if chosen and query.product_id is None:
            vocabulary = next(row[3] for row in index.rows if row[:2] == (chosen.product_id, chosen.attribute))
            # Novel modifiers can name an unknown provider/product; overlap cannot erase them.
            grammar = tokens("need require involve understand tell explain mean work procedure process")
            if tokens(query.raw_span) - vocabulary - grammar:
                chosen = None
        reason = "accepted" if chosen else "insufficient overlap or distinct-target margin"
    if trace is not None:
        trace.steps.append({"stage": "routing", "generation": index.generation, "reason": reason,
                            "candidates": [{"entity": r.product_id, "attribute": r.attribute,
                            "score": round(r.score, 6), "anchor_matches": r.anchor_matches} for r in ranked[:3]]})
    if chosen is None:
        return query
    routed = apply_route(query, chosen, index.latest_day)
    if trace is not None:
        trace.field("routed_entity", routed.product_id, Origin.INFERRED, "verified source lexical overlap")
        trace.field("routed_attribute", routed.attribute, Origin.INFERRED, "verified source lexical overlap")
    return routed
