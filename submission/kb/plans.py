"""Resolver plan helpers (spec sections 7.3-7.4): what a plan may print, where it came from, and the refusal plan.

``_bounds``, ``_date_tokens`` and ``_name_numbers`` give the number tokens a plan permits beyond its facts' value
texts and the question's numbers; ``_sources`` gives a plan's sources; ``_refusal`` is the digit-free refusal plan,
naming the asked thing in the question's words or ``that`` (``_refusal_span``); ``join_notes`` joins answer notes.
``EARLIEST_NOTE`` is the digit-free note of a plan whose ``as_of`` precedes the first crawl, which the composer prints
after the answer text (User decision 1). Leaf helpers: none calls into ``kb.resolve``, and this module imports
nothing from ``kb.resolve`` or ``kb.conflicts``, which import these names back (no cycle). Stdlib only, no I/O.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .normalize import number_tokens
from .question import Query
from .registry import Registry
from .store import FactStore
from .tiers import is_number, quals
from .types import AnswerPlan, Fact, Source

EARLIEST_NOTE = "Answered from the earliest website crawl available."  # holds no digit: adds no number to the text
_SPAN_CAP = 150
_UNSAFE_RE = re.compile(r"[{}<>*\\\s]+")  # composer-unsafe characters and every whitespace run become one space
_CUE_RE = re.compile(r"(?<![-\w])(?:interest rates?|rates?|apys?|aprs?|annual percentage (?:yield|rate)|yields?"
                     r"|dividends?|(?:lobby |drive-?(?:up|thru|through) )?hours|address(?:es)?|phone(?: numbers?)?"
                     r"|routing numbers?|fees?|minimums?|terms?|links?|urls?|websites?)\b", re.I)
_LEAD_RE = re.compile(r"^(?:(?:can|could|would|will) you (?:please )?\w+(?: me| us)?|what(?:'s| is| are| was| were)?"
                      r"|which|how(?: much| many)?|when|where|who|why|is|are|was|were|do|does|did|can|could|has|have"
                      r"|will|would|should)\b ?", re.I)
_VERB_RE = re.compile(r"\b(?:do|does|did|would|will|can|could|should) (?:you|i|we|members?) "
                      r"(?:charge|offer|pay|get|earn|give|have|list|use|see|find|need)\b ?", re.I)
_LINK_RE = re.compile(r"https?:|www\.|[a-z0-9-]\.(?:com|org|net|gov|edu|us|io|co|info|biz|bank)\b", re.I)  # URL, domain
_DETERMINERS = frozenset({"the", "a", "an"})
_OWNERS = frozenset({"your", "our", "its", "their", "dupaco's", "dupacos"})  # read as "the" in a refusal

Days = Dict[str, Optional[str]]  # snapshot_id -> the as_of its facts were read with


def _bounds(f: Fact) -> Set[Tuple[str, float]]:
    """Number tokens of a row's tier bounds: money tiers in dollars, model years, the term in months and years; and
    of the qualifiers a label prints, which a strict plan's lint checks: the ``year`` a count describes and the
    numbers of a ``branch_name`` (``Highway 151``)."""
    d = quals(f)
    money = ("balance_min", "balance_max", "loan_amount_max")
    plain = ("model_year_min", "model_year_max", "term_months", "year")
    out = {("$", round(float(d[n]), 4)) for n in money if is_number(d.get(n))}
    out |= {("", round(float(d[n]), 4)) for n in plain if is_number(d.get(n))}
    term = d.get("term_months")
    if is_number(term) and term % 12 == 0:
        out.add(("", round(term / 12, 4)))
    name = d.get("branch_name")
    if isinstance(name, str):
        out |= number_tokens(name)
    return out


def _date_tokens(as_of: Optional[str], crawl_days: Sequence[str]) -> Set[Tuple[str, float]]:
    """``("", year)`` of the plan's ISO ``as_of`` (an "As of May 2026" prefix), then the day and the year of each
    compared ISO crawl date (``on May 19, 2026``)."""
    out = {("", float(int(as_of[:4])))} if as_of else set()
    for day in crawl_days:
        out |= {("", float(int(day[:4]))), ("", float(int(day[8:10])))}
    return out


def _sources(store: FactStore, facts: Sequence[Fact], days: Days) -> Tuple[Source, ...]:
    """Each fact's source, then those of every in-force fact of its crawl with the same key and value text (the
    same row on other pages, whatever their date or authority), in rank order; each source once."""
    out: List[Source] = []
    for f in facts:
        crawl = f.source.snapshot_id
        copies = store.in_force(crawl, f.product_id, f.attribute, days.get(crawl))
        cut = days.get(crawl)
        semantic_cut = cut or dict(store.snapshots())[crawl]
        copies = [c for c in copies if not (c.semantics is not None or c.attribute == "fee")
                  or not c.effective_date or c.effective_date <= semantic_cut]
        for g in [f] + [c for c in copies if c.key == f.key and c.value_text == f.value_text and c.rate_bound == f.rate_bound
                        and (not f.published_date or c.published_date and c.published_date <= f.published_date
                             and (not cut or c.published_date <= cut))]:
            if g.source not in out:
                out.append(g.source)
    return tuple(out)


def _name_numbers(registry: Registry, product_id: str) -> Set[Tuple[str, float]]:
    """Number tokens of the product's display name, which each row label prints (``1st Rate Checking``)."""
    try:
        return number_tokens(registry.display_name(product_id))
    except KeyError:
        return set()


def _refusal_span(q: Query) -> str:
    """The question's own words for the asked thing: from the determiner before its first attribute word, or that
    word, to the end (``the HELOC intro APR``; ``your rate on the HELOC`` reads ``the rate on the HELOC``), else
    the question without its opening words; markup characters become spaces. ``that`` instead when the question
    names no recognised product (an unknown name is never restated: ``Jump Start``) or the span would hold a number,
    a URL or a domain (``still paying 2.25%``, ``7/1``): a should_refuse item may list any of them as a trap."""
    if q.product_id is None:
        return "that"
    text = _UNSAFE_RE.sub(" ", (q.raw_span or "").replace("’", "'")).strip().rstrip("?!. ")
    cue = _CUE_RE.search(text)
    if cue:
        before = text[:cue.start()].split()
        at = next((i for i in range(len(before) - 1, max(-1, len(before) - 5), -1)
                   if before[i].lower() in _DETERMINERS | _OWNERS), None)
        head = ["the"] if at is None or before[at].lower() in _OWNERS else [before[at]]
        text = " ".join(head + (before[at + 1:] if at is not None else []) + [_VERB_RE.sub("", text[cue.start():])])
    else:
        text = _VERB_RE.sub("", _LEAD_RE.sub("", text))
    span = text.strip()
    if len(span) > _SPAN_CAP:
        span = span[:_SPAN_CAP].rsplit(" ", 1)[0]
    span = span.rstrip(" ,;:-")
    return span if span and not number_tokens(span) and not _LINK_RE.search(span) else "that"


def _refusal(q: Query, snapshot_id: Optional[str]) -> AnswerPlan:
    return AnswerPlan(q.intent, (), frozenset(q.question_numbers), (), False, None, snapshot_id, _refusal_span(q),
                      q.as_of, question=q.raw_span)


def join_notes(*notes: Optional[str]) -> Optional[str]:
    """The non-empty notes joined with one space; ``None`` when there are none."""
    kept = [note for note in notes if note]
    return " ".join(kept) if kept else None
