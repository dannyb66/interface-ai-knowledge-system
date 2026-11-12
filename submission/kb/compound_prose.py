"""Two explicitly requested prose scopes for one entity, independently arbitrated."""
from __future__ import annotations

from dataclasses import replace
import re

ATTRIBUTES = ("eligibility", "description")
_ELIGIBILITY = re.compile(
    r"\b(?:eligib\w*|qualif\w*|requirements?)\b|"
    r"\bwho\b.{0,60}\b(?:use|access|join|participate|apply)\b|"
    r"\b(?:must|need|require\w*)\b.{0,60}\b(?:member\w*|belong)\b|"
    r"\bmember\w*\b.{0,40}\b(?:required|necessary)\b|"
    r"\bavailable\s+to\b|\b(?:nonmembers?|non-members?)\b", re.I)
_DESCRIPTION = re.compile(
    r"\bhow\b.{0,80}\b(?:deliver\w*|provided?|works?|operat\w*|help\w*)\b|"
    r"\b(?:what|which)\b.{0,80}\b(?:services?|features?|benefits?|delivery|licens\w*|geograph\w*)\b|"
    r"\b(?:explain|describe)\b.{0,60}\b(?:services?|features?|delivery|process|procedures?)\b", re.I)
_PERSONAL_VERDICT = re.compile(r"\b(?:am i|are we|(?:do|can|could|would|will) (?:i|we) qualify|"
                               r"(?:can|could|may) (?:i|we) (?:use|join|participate)|my eligibility|our eligibility)\b", re.I)
_NEXT_CLAUSE = frozenset("who what which how where when why is are do does must can should would will its "
                         "eligibility requirements service services delivery features benefits licensing geographic "
                         "describe explain membership members nonmembers".split())
_SCOPE_GRAMMAR = frozenset((
    "a an the and also plus who what which how where when why is are was were be been being do does did must can "
    "could may should would will i we you me us my our your its it this that these those of for from to with by in on "
    "at as or not no non all any both each only please tell give show explain describe find know about whether "
    "eligibility eligible qualify qualifies qualified qualification qualifications requirements requirement required "
    "necessary need needs require requires membership member members nonmember nonmembers belong use uses access "
    "join joins participate participates participation apply applies available availability service services feature "
    "features benefit benefits delivery deliver delivers delivered provide provides provided providing work works "
    "working operate operates operation operations help helps licensing licensed license licenses state states "
    "location locations geographic geographical geography agency program process procedures procedure company "
    "customer customers employee employees employer employers consumer consumers business people dupaco s "
    "am compare comparing agencies limits"
).split())


def unknown_compound_scope(query, registry):
    """A recognized subject in one clause cannot lend evidence to an unknown subject.

    This bounded two-scope grammar allows the recognized entity's aliases and
    ordinary request/reference words. Unresolved nouns or modifiers require a
    refusal, including when they follow "and what services does ...".
    """
    text = query.raw_span
    if (not query.explicit_entity or len(query.product_ids) != 1
            or query.attribute not in (None,) + ATTRIBUTES
            or not re.search(r"\b(?:and|also|plus)\b|[?;]", text, re.I)
            or not (_ELIGIBILITY.search(text) and _DESCRIPTION.search(text))):
        return False
    from .normalize import norm_text
    text = norm_text(text)
    aliases = [norm_text(alias) for alias, pid in registry.aliases().items() if pid == query.product_id]
    for alias in sorted(aliases, key=lambda value: (-len(value), value)):
        text = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", " ", text)
    return bool(set(re.findall(r"[a-z]+", text)) - _SCOPE_GRAMMAR)


def requested_attributes(query, explicit_attrs):
    """Recognize two semantic requests; publication is checked by each resolver arm.

    This never splits or rewrites the question. In particular, an unpublished
    request cannot disappear just because the other attribute has evidence.
    """
    if (not query.explicit_entity or query.route_blocked or len(query.product_ids) != 1
            or query.mentions or query.families or query.past or query.as_of_end or query.change_point
            or query.intent not in ("value", "yes_no", "how_to") or query.question_numbers
            or set(explicit_attrs) - set(ATTRIBUTES)
            or query.attribute not in (None,) + ATTRIBUTES):
        return ()
    text = query.raw_span
    if not re.search(r"\b(?:and|also|plus)\b|[?;]", text, re.I):
        return ()
    # A coordinator introducing another noun phrase may name an unrecognized
    # second provider/product. Never erase it to make this a one-entity request.
    continuations = re.findall(r"\b(?:and|also|plus)\s+(?:the\s+)?([a-z]+)\b", text, re.I)
    if any(word.lower() not in _NEXT_CLAUSE for word in continuations) or re.search(r"\b(?:they|them|their)\b", text, re.I):
        return ()
    return ATTRIBUTES if _ELIGIBILITY.search(text) and _DESCRIPTION.search(text) else ()


def resolve_compound(query, registry, resolve_one, trace=None):
    """Each arm keeps the original date, slots, numbers and wording; no partial answer."""
    from .diagnostics import RefusalReason, diagnosed
    from .plans import _refusal, join_notes

    valid = (query.requested_prose_attributes == ATTRIBUTES and query.product_id
             and query.product_ids in ((), (query.product_id,)) and not query.mentions
             and not query.families and not query.past and not query.as_of_end and not query.change_point
             and not _PERSONAL_VERDICT.search(query.raw_span))
    if not valid:
        return diagnosed(_refusal(query, None), trace, RefusalReason.AMBIGUOUS, query.product_id)
    plans = []
    for attr in query.requested_prose_attributes:
        part = replace(query, attribute=attr, requested_prose_attributes=(), intent="value",
                       generic_rate=False, explicit_attribute=True)
        plan = resolve_one(part)
        if trace is not None:
            trace.pool("compound_prose_attribute", plan.facts, plan.facts if plan.confident else (),
                       attribute=attr, confident=plan.confident)
        if not plan.confident or not plan.facts or any(f.attribute != attr for f in plan.facts):
            return _refusal(query, plan.snapshot_id)
        plans.append(plan)
    if len({plan.snapshot_id for plan in plans}) != 1:
        return _refusal(query, None)
    return replace(plans[0], intent="value", question=query.raw_span,
                   facts=tuple(f for plan in plans for f in plan.facts),
                   sources=tuple(dict.fromkeys(s for plan in plans for s in plan.sources)),
                   permitted_values=frozenset(v for plan in plans for v in plan.permitted_values),
                   strict_numbers=any(plan.strict_numbers for plan in plans),
                   conflict_note=join_notes(*(plan.conflict_note for plan in plans)),
                   requested_prose_attributes=query.requested_prose_attributes)


def complete_render(text, plan):
    """The final answer retains both labeled scopes and every selected statement."""
    if not plan.requested_prose_attributes:
        return True
    from .verify import page_text, quote_found
    from .prose_presentation import prose_statement
    normalized = page_text(text)
    return (set(f.attribute for f in plan.facts) == set(plan.requested_prose_attributes)
            and " eligibility:" in text and " service information:" in text
            and all(quote_found(prose_statement(f.value_text), normalized) for f in plan.facts))
