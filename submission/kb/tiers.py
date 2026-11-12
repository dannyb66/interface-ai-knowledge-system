"""Tier decision table (spec section 7.3): a product/attribute's current tiers and the selectors that narrow them.

``current``: the table rows when the product/attribute has any (inline sentences only otherwise), the top authority
class only, one fact per key in store rank order, and no tier of an older table that overlaps a tier of a newer one
(a stale page's ``2020-22`` model years beside the rate sheet's ``2021-22``).

``select_tier``: the qualifier filters, each tier kind through ``TIER_SELECTORS``, a soft jumbo preference, tier
order, then ``highest``/``lowest``. Bounds are inclusive and the narrowest tier containing the asked amount or model
year wins within each row family; explicit newest/latest model-year wording selects the highest available band
after term filtering; an open lower end (``$832,750 or less``) starts at 0 and an open upper end
(``$25,000+``) never ends; a two-digit model-year end takes the century of the lower bound; ``7/1`` is the ARM
program, never a term (the canonicaliser's ``program=arm`` matches no mortgage row); ``highest``/``lowest`` keep
the tier with the max/min value. An unasked tier is enumerated (term, model year, balance, jumbo), except that
``intro`` defaults to the standard rate, an asked amount at or above a jumbo row's minimum to earn (the resolver
reads the minimums) keeps that jumbo row in place of its regular one, and else an asked term without ``jumbo``
keeps the regular row. An asked ``special`` keeps special rows only, so a special question never answers with a
regular rate, except in a ``list``, where it orders instead (``including specials``: every row, the special ones
first); an asked ``jumbo`` is hard over tiered rows, a row without the flag being no jumbo row (a link with no
qualifier passes); a ``day`` only narrows, to the lines whose printed day range holds it (``day_range``: Wednesday
is in ``monday-thursday``); an asked ``year`` is hard over facts that carry one (the calendar year a count
describes), which enumerate newest first; a segment filters only when the question names one. ``misses`` reports
an asked qualifier that, applied alone, matches no tier: the resolver refuses on it (a jumbo mortgage). Stdlib
only, no I/O.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from .extract_rules import TABLE_CONFIDENCE
from .lexicon import DAYS
from .question import Query
from .types import Fact
from .conditions import select_conditions

_INF = float("inf")
_RANGES = {"balance": ("balance_min", "balance_max"), "loan_amount": (None, "loan_amount_max"),
           "model_year": ("model_year_min", "model_year_max")}
_RANGE_NAMES = frozenset({"balance_min", "balance_max", "loan_amount_max", "model_year_min", "model_year_max"})
_FLAGS = ("intro", "jumbo", "special")  # boolean qualifiers: a missing one reads as False
_STREET = {"avenue": "ave", "street": "st", "road": "rd", "drive": "dr", "lane": "ln", "boulevard": "blvd",
           "court": "ct", "highway": "hwy", "parkway": "pkwy"}
_STREET_TYPES = frozenset({"ave", "st", "rd", "dr", "blvd", "ln", "hwy"})  # branch_named ignores them (as _STREET maps)
_PERSONAL_RE = re.compile(r"\bpersonal\b", re.I)

Selector = Callable[[Sequence[Fact], Query], List[Fact]]
Minimums = Mapping[Tuple[Tuple[str, Any], ...], float]  # a jumbo row's qualifiers -> its minimum to earn


def slot(q: Query, name: str) -> Any:
    """The value of slot ``name``, or ``None``."""
    return dict(q.slots).get(name)


def quals(f: Fact) -> Dict[str, Any]:
    """The fact's qualifiers as a dict."""
    return dict(f.qualifiers)


def is_number(value: Any) -> bool:
    """An int or float qualifier value (a bool is not a number here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _carries(facts: Sequence[Fact], name: str) -> bool:
    return any(key == name for f in facts for key, _ in f.qualifiers)


def _flag(f: Fact, name: str) -> bool:
    return bool(quals(f).get(name, False))


def _num(d: Dict[str, Any], name: str) -> float:
    return float(d[name]) if is_number(d.get(name)) else 0.0


def _span(f: Fact, kind: str) -> Optional[Tuple[float, float]]:
    """``(low, high)`` of the fact's ``kind`` tier, both inclusive (an open low end is 0, an open high end is
    infinite), or ``None`` when the fact has no such tier."""
    d = quals(f)
    low_name, high_name = _RANGES[kind]
    low, high = (d.get(low_name) if low_name else None), d.get(high_name)
    if not is_number(low) and not is_number(high):
        return None
    low = float(low) if is_number(low) else 0.0
    high = float(high) if is_number(high) else _INF
    if kind == "model_year" and high < 100 <= low:  # "2023-26": the century of the lower bound
        high += low // 100 * 100
    return low, high


def _row_family(f: Fact) -> Tuple[Tuple[str, Any], ...]:
    """The qualifiers that are not tier ranges, flags defaulting to False: the tiers of one row family share it."""
    d = {name: value for name, value in f.qualifiers if name not in _RANGE_NAMES}
    for name in _FLAGS:
        d[name] = bool(d.get(name, False))
    return tuple(sorted(d.items(), key=lambda pair: pair[0]))


def _overlaps(a: Fact, b: Fact) -> bool:
    """Same row family and every tier range intersecting; a missing range is unbounded."""
    if _row_family(a) != _row_family(b):
        return False
    for kind in sorted(_RANGES):
        sa, sb = _span(a, kind), _span(b, kind)
        if sa is not None and sb is not None and (sa[1] < sb[0] or sb[1] < sa[0]):
            return False
    return True


def current(facts: Sequence[Fact], trace=None) -> List[Fact]:
    """The current tiers of one product/attribute from ``FactStore.in_force`` output (best rank first): table rows
    when any exist, the top authority class, the first fact of each key, then no older-table tier overlapping a
    kept newer one (rank puts newer effective dates first within an authority class)."""
    pool = [f for f in facts if f.confidence >= TABLE_CONFIDENCE] or list(facts)
    if trace is not None:
        trace.pool("source_quality", facts, pool, rule="prefer table confidence when present")
    if not pool:
        return []
    top = max(f.source.authority for f in pool)
    if trace is not None:
        trace.pool("authority", pool, [f for f in pool if f.source.authority == top], authority=top)
    kept: List[Fact] = []
    seen: Set[Any] = set()
    for f in pool:
        if f.source.authority != top or f.key in seen:
            continue
        seen.add(f.key)
        if not any(k.effective_date != f.effective_date and _overlaps(k, f) for k in kept):
            kept.append(f)
    if trace is not None:
        trace.pool("current_keys", [f for f in pool if f.source.authority == top], kept,
                   rule="one ranked fact per key; discard older overlapping tiers")
    return kept


def _tier_key(f: Fact) -> Tuple[Any, ...]:
    """Explicit enumeration order: program, year newest first, branch, day, special, intro, term ascending, model
    years newest first, balance and loan amount ascending, jumbo after regular, then the text and the page."""
    d = quals(f)
    return (str(d.get("program", "")), -_num(d, "year"), str(d.get("branch_name", "")), str(d.get("day", "")),
            bool(d.get("special", False)), bool(d.get("intro", False)), _num(d, "item"), _num(d, "term_months"),
            -_num(d, "model_year_max"), _num(d, "balance_min"), _num(d, "loan_amount_max"),
            bool(d.get("jumbo", False)), f.value_text, f.source.canonical_url)


def _narrowest(facts: Sequence[Fact], asked: Optional[float], kind: str) -> List[Fact]:
    """Facts whose ``kind`` tier contains ``asked``, only the narrowest per row family; facts without a ``kind``
    tier pass through. Unchanged when nothing is asked or no fact has a ``kind`` tier."""
    spans = [(f, _span(f, kind)) for f in facts]
    if asked is None or all(span is None for _, span in spans):
        return list(facts)
    width: Dict[Tuple[Tuple[str, Any], ...], float] = {}
    for f, span in spans:
        if span is not None and span[0] <= asked <= span[1]:
            family = _row_family(f)
            width[family] = min(width.get(family, _INF), span[1] - span[0])
    return [f for f, span in spans if span is None or (
        span[0] <= asked <= span[1] and span[1] - span[0] == width[_row_family(f)])]


def _select_balance(facts: Sequence[Fact], q: Query) -> List[Fact]:
    return _narrowest(facts, slot(q, "amount"), "balance")


def _select_loan_amount(facts: Sequence[Fact], q: Query) -> List[Fact]:
    return _narrowest(facts, slot(q, "amount"), "loan_amount")


def _select_model_year(facts: Sequence[Fact], q: Query) -> List[Fact]:
    narrowed = _narrowest(facts, slot(q, "model_year"), "model_year")
    spans = [(f, _span(f, "model_year")) for f in narrowed]
    available = [span for _, span in spans if span is not None]
    if not slot(q, "latest_model_year") or not available:
        return narrowed
    newest = max(available, key=lambda span: (span[1], span[0]))
    return [f for f, span in spans if span == newest]


def _select_term(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """The asked term only; ``7/1`` never arrives here (the canonicaliser reads it as ``program=arm``)."""
    term = slot(q, "term_months")
    if term is None or not _carries(facts, "term_months"):
        return list(facts)
    return [f for f in facts if quals(f).get("term_months") == term]


def named_segment(q: Query) -> Optional[str]:
    """The one segment the question names: business wording always sets the slot, while ``personal`` is the
    canonicaliser's default and counts only when the word is there; ``None`` (no segment, or both named) orders
    rather than filters."""
    segment = slot(q, "segment")
    personal = bool(_PERSONAL_RE.search(q.raw_span or ""))
    if (segment == "personal" and not personal) or (segment == "business" and personal):
        return None
    return segment


def _select_segment(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """Facts that carry a ``segment`` qualifier must match the segment the question names."""
    segment = named_segment(q)
    if segment is None or not _carries(facts, "segment"):
        return list(facts)
    return [f for f in facts if quals(f).get("segment", segment) == segment]


def _select_program(facts: Sequence[Fact], q: Query) -> List[Fact]:
    program = slot(q, "program")
    if program is None or not _carries(facts, "program"):
        return list(facts)
    return [f for f in facts if quals(f).get("program") == program]


def _select_jumbo(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """Hard over tiered rows: a row without the flag reads as not jumbo, so ``jumbo`` asked of a product whose rows
    have no jumbo tier (a jumbo mortgage) leaves nothing and the resolver refuses. Facts with no qualifier at all (a
    link, a description) are no tiers and pass."""
    jumbo = slot(q, "jumbo")
    if jumbo is None or not any(f.qualifiers for f in facts):
        return list(facts)
    return [f for f in facts if _flag(f, "jumbo") == jumbo]


def _select_special(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """An asked ``special`` keeps the special rows only: a special question never answers with a regular rate. A
    ``list`` keeps every row (``_special_first`` orders them)."""
    special = slot(q, "special")
    if special is None or q.intent == "list" or not _carries(facts, "special"):
        return list(facts)
    return [f for f in facts if _flag(f, "special") == special]


def _special_first(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """For a ``list`` asking ``special``, the rows of the asked kind first; a stable sort, so tier order holds
    within each kind."""
    special = slot(q, "special")
    if special is None or q.intent != "list":
        return list(facts)
    return sorted(facts, key=lambda f: _flag(f, "special") != special)


def _select_intro(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """The asked rate period; unasked, the standard rate unless the product lists only an intro rate."""
    intro = slot(q, "intro")
    if intro is None:
        return [f for f in facts if not _flag(f, "intro")] or list(facts)
    return [f for f in facts if _flag(f, "intro") == intro]


def _name_words(text: Any) -> FrozenSet[str]:
    return frozenset(_STREET.get(word, word) for word in re.findall(r"[a-z0-9]+", str(text).lower()))


def branch_named(facts: Sequence[Fact], name: Any) -> List[Fact]:
    """Facts whose branch name (street and city) holds every word of ``name`` other than its street-type words
    (``_STREET_TYPES``), which a stored name's street part may lack: "East Washington Avenue" finds ``east washington,
    madison``, and ``galena`` finds ``oldenburg ln., galena``. A stored name without a street part (no ", ": a city or a
    store, ``asbury``, ``platteville``) must hold the asked street-type words too, so "the Asbury Road branch" (Dubuque)
    is not the closed ``asbury`` one (Task 13). A name of street-type words alone ("the Main Street branch") and a fact
    without a branch name match nothing."""
    asked = _name_words(name)
    wanted = asked - _STREET_TYPES
    def holds(stored: str) -> bool:
        words = _name_words(stored)
        return bool(wanted) and wanted <= words and (", " in stored or asked & _STREET_TYPES <= words)
    return [f for f in facts if holds(str(quals(f).get("branch_name", "")))]


def _select_branch(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """The asked branch (``branch_named``) when the facts name branches; the resolver refuses a contact question
    naming a branch no branch fact carries."""
    name = slot(q, "branch_name")
    if name is None or not _carries(facts, "branch_name"):
        return list(facts)
    return branch_named(facts, name)


def day_range(label: str) -> FrozenSet[str]:
    """The day names a ``day`` qualifier covers: ``monday-thursday`` the four days from Monday to Thursday,
    ``saturday-sunday`` both, ``friday`` itself; a range that wraps (``friday-monday``) runs through the weekend. Any
    other label stands for itself, so it still matches only an equal asked day."""
    ends = str(label).split("-")
    if not all(end in DAYS for end in ends) or len(ends) > 2:
        return frozenset({label})
    first, last = DAYS.index(ends[0]), DAYS.index(ends[-1])
    return frozenset(DAYS[(first + k) % len(DAYS)] for k in range((last - first) % len(DAYS) + 1))


def _select_day(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """Soft: only facts that carry a ``day`` qualifier are filtered, to those whose ``day_range`` holds the asked
    day, and a day matching none keeps every fact, so a day never refuses."""
    day = slot(q, "day")
    if day is None:
        return list(facts)
    return [f for f in facts if day in day_range(quals(f).get("day", day))] or list(facts)


def _select_year(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """Hard over facts that carry a ``year`` (the calendar year a count describes): the asked year only, so a year
    no fact describes leaves none and the resolver refuses (``misses``); facts carrying none pass, the asked year
    then cutting their publication dates instead (``kb.temporal.cutoff``)."""
    year = slot(q, "year")
    if year is None or not _carries(facts, "year"):
        return list(facts)
    return [f for f in facts if quals(f).get("year") == year]


def _plain_family(f: Fact) -> Tuple[Tuple[str, Any], ...]:
    """The row family without the jumbo flag: a jumbo row and the regular row of its term share it."""
    return tuple(pair for pair in _row_family(f) if pair[0] != "jumbo")


def _prefer(facts: Sequence[Fact], q: Query, minimums: Minimums) -> List[Fact]:
    """Soft, once the tiers are cut, without an asked ``jumbo``: an asked amount at or above a jumbo row's minimum
    to earn (``minimums``, keyed by its qualifiers) keeps that jumbo row in place of the regular row of its family,
    and every other family its regular rows (``$100,000 or more`` earns the jumbo rate). Otherwise an asked term
    keeps the regular row when there is one, since the jumbo row of that term is another tier (a jumbo value is a
    trap for a plain 17-month question)."""
    if slot(q, "jumbo") is not None:
        return list(facts)
    amount = slot(q, "amount")
    earned = {_plain_family(f) for f in facts if _flag(f, "jumbo") and is_number(amount)
              and amount >= minimums.get(f.qualifiers, _INF)}
    if earned:
        return [f for f in facts if _flag(f, "jumbo") == (_plain_family(f) in earned)]
    if slot(q, "term_months") is not None:
        return [f for f in facts if not _flag(f, "jumbo")] or list(facts)
    return list(facts)


def _superlative(facts: Sequence[Fact], q: Query) -> List[Fact]:
    """``highest``/``lowest``: the first tier (in tier order) holding the max/min value."""
    which = slot(q, "superlative")
    valued = [f for f in facts if f.value is not None]
    if which not in ("highest", "lowest") or not valued:
        return list(facts)
    target = max(f.value for f in valued) if which == "highest" else min(f.value for f in valued)
    return [next(f for f in valued if f.value == target)]


TIER_SELECTORS: Dict[str, Selector] = {"balance": _select_balance, "term": _select_term,
                                       "loan_amount": _select_loan_amount, "model_year": _select_model_year,
                                       "segment": _select_segment}
QUALIFIER_FILTERS: Dict[str, Selector] = {"program": _select_program, "branch_name": _select_branch,
                                          "day": _select_day, "jumbo": _select_jumbo, "special": _select_special,
                                          "intro": _select_intro, "year": _select_year, "conditions": select_conditions}
_TIER_ORDER = ("term", "model_year", "balance", "loan_amount", "segment")
_FILTER_ORDER = ("program", "branch_name", "day", "jumbo", "special", "intro", "year", "conditions")
_HARD_TIERS = ("term", "model_year", "balance", "loan_amount")  # an asked tier of these kinds can refuse


def select_tier(facts: List[Fact], q: Query, minimums: Optional[Minimums] = None, trace=None) -> List[Fact]:
    """The decision table over one product's current tiers: the qualifier filters, each tier kind through
    ``TIER_SELECTORS``, the soft jumbo preference (``minimums``: each jumbo row's minimum to earn, by qualifiers),
    tier order (a list's asked special kind first), then ``highest``/``lowest``."""
    out = list(facts)
    for name in _FILTER_ORDER:
        before, out = out, QUALIFIER_FILTERS[name](out, q)
        if trace is not None:
            trace.pool("qualifier:" + name, before, out, asked=slot(q, name))
    for kind in _TIER_ORDER:
        before, out = out, TIER_SELECTORS[kind](out, q)
        if trace is not None:
            trace.pool("tier:" + kind, before, out)
    chosen = _superlative(_special_first(sorted(_prefer(out, q, minimums or {}), key=_tier_key), q), q)
    if trace is not None:
        trace.pool("preference_and_order", out, chosen)
    return chosen


def misses(q: Query, facts: Sequence[Fact]) -> bool:
    """Some asked qualifier, applied alone, leaves none of ``facts``."""
    return (any(not QUALIFIER_FILTERS[name](facts, q) for name in _FILTER_ORDER)
            or any(not TIER_SELECTORS[kind](facts, q) for kind in _HARD_TIERS))
