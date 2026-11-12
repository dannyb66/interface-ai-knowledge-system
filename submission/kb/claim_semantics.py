"""Versioned annotations for reviewed prose; structural checks never replace source review."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence, Tuple

from .normalize import canonical_url, number_tokens
from .verify import page_text, quote_found, value_in_quote
from .source_quality import quality_reason

UNITS = frozenset({"text", "usd", "count", "percent", "percentage_points", "free"})
ROLES = {"eligibility_condition": {"eligibility"}, "fee": {"fee"},
         "benefit": {"description"}, "organization_fact": {"description", "count"},
         "procedure": {"description"}, "description": {"description"}}
COMPARATORS = frozenset({"none", "eq", "lt", "le", "gt", "ge"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PP = re.compile(r"\bpercentage[ -]+points?\b", re.I)
_PERCENT = re.compile(r"%|\bpercent\b", re.I)
_RATE = re.compile(r"\b(?:APY|APR|annual percentage (?:yield|rate))\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])(?P<currency>\$)?\s*(?P<number>\d[\d,]*(?:\.\d+)?)"
                     r"(?P<unit>\s*(?:percentage[ -]+points?\b|%|percent\b))?", re.I)
_BOUNDS = (("le", r"at or below|up to|(?:no|not) more than|maximum(?: of)?|at most|less than or equal to", r"or less|or below"),
           ("ge", r"at least|minimum(?: of)?|at or above|(?:no|not) less than|greater than or equal to", r"or more|or above"),
           ("lt", r"less than|below|under", r""), ("gt", r"more than|above|over|greater than", r""))


def primary_comparator(text: str, value: Optional[float], unit: str) -> str:
    matches = []
    for match in _NUMBER.finditer(text):
        suffix = (match.group("unit") or "").strip().lower()
        observed = "usd" if match.group("currency") else "percentage_points" if _PP.fullmatch(suffix) else "percent" if suffix else "count"
        if value is not None and float(match.group("number").replace(",", "")) == value and observed == unit:
            matches.append(match)
    if len(matches) != 1:
        raise ValueError("comparator requires one unambiguous primary numeric claim")
    match = matches[0]
    before, after = text[:match.start()].rstrip(), text[match.end():].lstrip()
    for kind, left, right in _BOUNDS:  # inclusive phrases win before their strict suffixes
        if re.search(r"\b(?:" + left + r")\s*$", before, re.I) or right and re.match(r"(?:" + right + r")\b", after, re.I):
            return kind
    return "eq"


@dataclass(frozen=True)
class SourcePin:
    snapshot_id: str
    raw_url: str
    content_sha256: str


@dataclass(frozen=True)
class ClaimSemantics:
    version: int
    claim_id: str
    revision: str
    role: str
    comparator: str
    basis: str
    condition_group: str
    condition_logic: str
    conditions: Tuple[str, ...]
    numeric_unit: str
    scale: str


def comparison_value(fact: Any) -> Any:
    """Typed meaning includes the full claim, not just its primary number.

    Publication/capture changes remain evidence dates, not changes to the statement.
    Legacy numeric formatting retains numeric equality; explicit rate bounds remain meaningful.
    """
    semantic = fact.semantics
    if semantic is None:
        return (fact.value if fact.value is not None else fact.value_text, fact.rate_bound)
    return (fact.value, fact.value_text, fact.unit, semantic.role, semantic.comparator, semantic.basis,
            semantic.condition_group, semantic.condition_logic, semantic.conditions, semantic.scale)


def parse_pins(raw: Any, crawls: Sequence[str], urls: Sequence[str]) -> Tuple[SourcePin, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("v2 source_pins must be a nonempty list")
    pins = []
    for row in raw:
        if not isinstance(row, dict) or set(row) != set(SourcePin.__dataclass_fields__):
            raise ValueError("invalid source pin fields")
        if (row["snapshot_id"] not in crawls or not isinstance(row["raw_url"], str)
                or not row["raw_url"].startswith("https://") or canonical_url(row["raw_url"]) not in urls
                or not isinstance(row["content_sha256"], str) or not _SHA.fullmatch(row["content_sha256"])):
            raise ValueError("source pin does not match its declared crawl/URL/content hash")
        pins.append(SourcePin(**row))
    if len(pins) != len(set(pins)):
        raise ValueError("duplicate source pin")
    if {(p.snapshot_id, canonical_url(p.raw_url)) for p in pins} != {(sid, url) for sid in crawls for url in urls}:
        raise ValueError("every declared page/crawl needs a source pin")
    return tuple(sorted(pins, key=lambda p: (p.snapshot_id, p.raw_url, p.content_sha256)))


def semantic_revision(quote: str, value_text: str, pins: Sequence[SourcePin], effective_date: Optional[str]) -> str:
    payload = [quote, value_text, [asdict(pin) for pin in sorted(pins, key=lambda p: (p.snapshot_id, p.raw_url, p.content_sha256))], effective_date]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def semantics_from_dict(raw: Mapping[str, Any]) -> ClaimSemantics:
    if not isinstance(raw, dict) or set(raw) != set(ClaimSemantics.__dataclass_fields__):
        raise ValueError("invalid semantic annotation fields")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ValueError("unknown semantic annotation version")
    if any(not isinstance(raw[name], str) for name in ClaimSemantics.__dataclass_fields__ if name not in ("version", "conditions")):
        raise ValueError("semantic annotation values must be strings")
    if not _ID.fullmatch(raw["claim_id"]) or not _SHA.fullmatch(raw["revision"]):
        raise ValueError("invalid claim identity/revision")
    if raw["role"] not in ROLES or raw["numeric_unit"] not in UNITS or raw["comparator"] not in COMPARATORS:
        raise ValueError("unknown semantic role, unit or comparator")
    if raw["condition_logic"] not in ("single", "all", "any"):
        raise ValueError("invalid condition logic")
    conditions = raw["conditions"]
    if not isinstance(conditions, (list, tuple)) or any(not isinstance(c, str) or not c.strip() for c in conditions):
        raise ValueError("conditions must be nonempty source-preserved strings")
    if len(conditions) != len(set(conditions)) or raw["condition_logic"] == "single" and len(conditions) > 1:
        raise ValueError("invalid condition set")
    if raw["condition_group"] and not _ID.fullmatch(raw["condition_group"]):
        raise ValueError("invalid condition group")
    return ClaimSemantics(**{**raw, "conditions": tuple(conditions)})


def validate_semantics(semantic: ClaimSemantics, quote: str, value_text: str, unit: str,
                       value: Optional[float], attribute: str) -> None:
    if not quote_found(value_text, page_text(quote)) or not value_in_quote(value_text, quote):
        raise ValueError("semantic statement is absent from its source quote")
    if attribute not in ROLES[semantic.role] or semantic.numeric_unit != unit:
        raise ValueError("semantic role/unit disagrees with fact")
    quality = quality_reason(value_text, unit, semantic.role)
    if quality:
        raise ValueError(quality)
    if semantic.role == "eligibility_condition" and (not semantic.condition_group or not semantic.conditions):
        raise ValueError("eligibility needs a complete named condition group")
    normalized = page_text(value_text)
    if any(not quote_found(condition, normalized) for condition in semantic.conditions):
        raise ValueError("rendered value omits a required condition")
    if semantic.basis and not quote_found(semantic.basis, normalized):
        raise ValueError("named basis is absent from the preserved statement")
    if semantic.scale and not quote_found(semantic.scale, normalized):
        raise ValueError("scale is absent from the preserved statement")
    if semantic.comparator != "none" and primary_comparator(value_text, value, unit) != semantic.comparator:
        raise ValueError("comparator disagrees with the primary numeric claim")
    if len(semantic.conditions) > 1 and not re.search(
            r"\b(?:and|both|all|each)\b" if semantic.condition_logic == "all" else r"\b(?:or|either|any)\b", value_text, re.I):
        raise ValueError("condition logic lacks source-preserved wording")
    if unit in ("text", "free"):
        if value is not None:
            raise ValueError("text/free facts have no invented numeric value")
        if unit == "free" and (semantic.role != "fee" or not re.search(r"\b(?:free|no charge)\b", value_text, re.I)):
            raise ValueError("free unit requires an explicit fee statement")
    else:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("semantic numeric value must be finite")
        token_unit = "$" if unit == "usd" else "%" if unit == "percent" else ""
        token_text = _PP.sub("", value_text) if unit == "percentage_points" else value_text
        if (token_unit, float(value)) not in number_tokens(token_text):
            raise ValueError("semantic numeric unit/value does not match source wording")
    if unit == "percentage_points" and (not _PP.search(value_text) or "%" in value_text):
        raise ValueError("percentage points cannot be represented as percent")
    if unit == "percent" and _PP.search(value_text):
        raise ValueError("percentage-point statement is not a percentage")
    if attribute == "eligibility" and (_PERCENT.search(quote) or _PP.search(quote)):
        if semantic.role != "eligibility_condition" or unit != "percent" or not semantic.basis or semantic.comparator == "none":
            raise ValueError("percentage eligibility needs a typed threshold and exact named basis")
    if attribute == "description" and (_PERCENT.search(quote) or _PP.search(quote)):
        typed_prose = semantic.role in ("procedure", "organization_fact") and unit == "percent"
        if typed_prose:
            percentages = [m for m in _NUMBER.finditer(value_text) if (m.group("unit") or "").strip().lower() in ("%", "percent")]
            if (not semantic.basis or not semantic.conditions or semantic.comparator == "none"
                    or len(percentages) != 1 or semantic.role == "procedure" and not semantic.condition_group):
                raise ValueError("percentage procedure/event needs one typed primary value, basis and complete conditions")
        if ((not typed_prose and (semantic.role != "benefit" or unit not in ("percent", "percentage_points")))
                or _RATE.search(quote)):
            raise ValueError("description cannot contain an advertised rate")
    if unit == "text" and (_PERCENT.search(value_text) or _PP.search(value_text)):
        raise ValueError("percentage text needs an explicit numeric role")


def semantics_survive(text: str, facts: Sequence[Any]) -> bool:
    """A v2 statement and every declared condition must survive composition/lint intact."""
    normalized = page_text(text)
    from .fee_semantics import presentation_statement, scope_survives
    from .source_attribution import attribution
    from .prose_presentation import prose_statement
    if not scope_survives(text, facts):
        return False
    for fact in facts:
        statement = presentation_statement(fact, facts)
        conditions = fact.semantics.conditions if fact.semantics is not None else ()
        if fact.attribute in ("description", "eligibility"):
            statement = prose_statement(statement)
            conditions = tuple(prose_statement(condition) for condition in conditions)
        if fact.attribute == "fee" and statement != fact.value_text:
            conditions = tuple(c.replace("*", "") for c in conditions)
        if fact.semantics is not None and (not quote_found(statement, normalized)
                or any(not quote_found(condition, normalized) for condition in conditions)
                or attribution(fact) and not quote_found(attribution(fact), normalized)):
            return False
    return True


def compatible_question(plan: Any) -> bool:
    """Typed verdicts cannot discard required conditions or infer personal eligibility."""
    if plan.intent != "yes_no":
        return True
    question = plan.question or ""
    asks_percent = bool(re.search(r"%|\bpercent\b", question, re.I))
    asks_points = bool(_PP.search(question))
    annotations = [f.semantics for f in plan.facts if f.semantics is not None]
    units = {annotation.numeric_unit for annotation in annotations}
    if "percentage_points" in units and asks_percent or "percent" in units and asks_points:
        return False
    for annotation in annotations:
        if annotation.role == "eligibility_condition":
            if re.search(r"\b(?:i|we|my|our|me|us)\b", question, re.I):
                return False
            if any(not quote_found(condition, page_text(question)) for condition in annotation.conditions):
                return False
        if len(annotation.conditions) > 1:
            changed = r"\b(?:or|either)\b" if annotation.condition_logic == "all" else r"\b(?:and|both)\b"
            if re.search(changed, question, re.I):
                return False
    return True
