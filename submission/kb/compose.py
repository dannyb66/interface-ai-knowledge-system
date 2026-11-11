"""Grounded templates for value, temporal, contact and refusal answers."""
from __future__ import annotations

import re
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from contract import Answer
from contract import Source as AnswerSource

from .compose_prose import (HOURS_NOTE, branch_display, render_alternatives, render_hours,  # HOURS_NOTE: re-exported
                            render_status)
from .labels import Row, label, phrase, product_names, sentence
from .lint import VALUE_UNITS, grounded, lint, strip_residue
from .normalize import number_tokens, question_amount
from .resolve import PAST
from .types import AnswerPlan, Fact, FactKey
from .compose_prose import render_prose

# Straight apostrophes only: harness/scoring.py REFUSAL_RE matches "can't", not a curly quote.
REFUSAL_TEMPLATE = "Dupaco's website doesn't list {span}, so I can't confirm it. Please contact Dupaco."
_FALLBACK_SPAN = "that"  # the refusal of a plan that carries no span of its own
_VERDICTS = ("Yes. ", "No. ")  # a yes/no answer's opening word; "As of" goes after it
# Change and past answers date their own crawls; hours carry no date (decision 3); a status line prints its own date.
_UNDATED = ("change", PAST, "hours", "status")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")  # fixed English names: calendar.month_name follows the locale
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# A yes/no question that compares ("below 12%") gets the grounding rows without a verdict word; whole words only,
# so "overdraft" and "understand" are no comparison.
_COMPARISON_RE = re.compile(r"\b(?:above|below|over|under|(?:more|less|higher|lower) than|at (?:least|most))\b", re.I)


def refusal(span: str) -> Answer:
    """The scorer-safe refusal: ``confident=False``, a REFUSAL_RE phrase, no digit beyond ``span``'s."""
    return Answer(text=REFUSAL_TEMPLATE.format(span=span), confident=False)


def _rows(facts: Sequence[Fact]) -> List[Row]:
    """Facts grouped into table rows in plan order: a fact joins the row before it when it is another column of
    that row (same product, qualifiers and crawl), as the resolver places a rate's APR right after the rate."""
    rows: List[List[Fact]] = []
    for f in facts:
        last = rows[-1] if rows else []
        same_row = bool(last) and (last[0].product_id, last[0].qualifiers, last[0].source.snapshot_id) == (
            f.product_id, f.qualifiers, f.source.snapshot_id)
        if same_row and all(g.attribute != f.attribute for g in last):
            last.append(f)
        else:
            rows.append([f])
    return [tuple(row) for row in rows]


def _table(plan: AnswerPlan) -> str:
    """Each row as ``{label}: {value_text} {unit}.``, one line per row in plan order."""
    names = product_names()
    rows = _rows(plan.facts)
    text = "\n".join(sentence("{}: {}".format(label(row[0], names), phrase(row))) for row in rows)
    question = (plan.question or "").lower()
    if len(rows) == 2 and "which" in question and all(row[0].value is not None for row in rows):
        lower = bool(re.search(r"\b(?:less|lower|cheaper)\b", question))
        if lower or re.search(r"\b(?:more|higher|better)\b", question):
            a, b = (row[0].value for row in rows)
            verdict = "Both are the same." if a == b else "The {} one is {}.".format(
                "first" if (a < b if lower else a > b) else "second", "lower" if lower else "higher")
            text += "\n" + verdict
    if plan.intent == "list" and re.search(r"\ball\b.*\bloan rates\b", question):
        text = "Lowest current rate for each loan:\n" + text
    return text


def _branch(f: Fact) -> Optional[str]:
    """The fact's branch as the address and phone lines print it (``compose_prose.branch_display``), else ``None``."""
    name = dict(f.qualifiers).get("branch_name")
    return branch_display(name) if name else None


def _date(text: Optional[str], permitted: FrozenSet[Tuple[str, float]], with_day: bool) -> Optional[str]:
    """``May 12, 2026`` (``with_day``) or ``May 2026`` from the first ISO date in ``text`` (a snapshot id such as
    ``01_2026-05-12_baseline`` embeds its crawl date); ``None`` without a date or when ``permitted`` lacks one of
    its numbers, so no template prints a date the plan does not permit."""
    m = _DATE_RE.search(text or "")
    if m is None or not 1 <= int(m.group(2)) <= 12:
        return None
    month = _MONTHS[int(m.group(2)) - 1]
    words = "{} {}, {}".format(month, int(m.group(3)), m.group(1)) if with_day else "{} {}".format(month, m.group(1))
    return words if number_tokens(words) <= permitted else None


def _on(snapshot_id: str, plan: AnswerPlan) -> str:
    day = _date(snapshot_id, plan.permitted_values, True)
    if day:
        return "on " + day
    return "in the latest crawl" if snapshot_id == plan.snapshot_id else "in an earlier crawl"


def _values(row: Row) -> Tuple[Tuple[str, object], ...]:
    return tuple((f.attribute, f.value if f.value is not None else f.value_text) for f in row)


def _question(plan: AnswerPlan) -> Optional[str]:
    """The question's text when the plan carries it (``AnswerPlan.question``: the parser's ``raw_span``, passed
    through by the resolver), else ``None``; ``getattr`` keeps a plan without that field working as before."""
    text = getattr(plan, "question", None)
    return text if isinstance(text, str) else None


def _claims_differ(plan: AnswerPlan, names: Mapping[str, str]) -> bool:
    """Whether the question claims a value no row shows as its own: a number in the unit of the rows' values that
    is neither a row's asked value (``row[0]``: the APR beside a rate is no match for a claimed rate) nor in its
    label. The claims are the numbers of the question's text when the plan carries it; without it, the permitted
    numbers that no fact and no label produced, which only the question can have brought."""
    rows = _rows(plan.facts)
    own: Set[Tuple[str, float]] = set()
    for row in rows:
        own |= number_tokens(row[0].value_text) | number_tokens(label(row[0], names))
    units = {unit for row in rows for unit, _ in number_tokens(row[0].value_text) if unit in VALUE_UNITS}
    question = _question(plan)
    if question is None:
        claims = plan.permitted_values - {token for f in plan.facts for token in number_tokens(f.value_text)}
    else:
        claims = frozenset(number_tokens(question))
    return any(unit in units and (unit, value) not in own for unit, value in claims)


def render_value(plan: AnswerPlan) -> str:
    """``{label}: {value_text} {unit}.``; enumerated tiers one line each."""
    return _table(plan)


def render_list(plan: AnswerPlan) -> str:
    """One line per row in plan order: every product the resolver enumerated (personal first), no question back."""
    return _table(plan)


def render_yes_no(plan: AnswerPlan) -> str:
    """``No.`` when the question claims a value no row shows as its own, else ``Yes.``, then the grounding rows; a
    question with a comparison word (``below 12%``, ``_COMPARISON_RE``) gets the rows alone, as it asks no equality.
    A claimed number is printed only where a row shows it (a hidden item may list the claim as a trap)."""
    question = _question(plan)
    if question and plan.facts and all(f.attribute in ("min_to_open", "min_to_earn") for f in plan.facts):
        amount = question_amount(question.lower())
        minima = [f.value for f in plan.facts if f.value is not None]
        if amount is not None and minima and re.search(r"\b(?:with|enough)\b", question, re.I):
            return ("Yes. " if amount >= min(minima) else "No. ") + _table(plan)
    if question is not None and _COMPARISON_RE.search(question):
        return _table(plan)
    return ("No. " if _claims_differ(plan, product_names()) else "Yes. ") + _table(plan)


def render_url(plan: AnswerPlan) -> str:
    """``{label}: {url}`` per fact, the URL left bare so it copies without punctuation."""
    names = product_names()
    text = "\n".join("{}: {}".format(label(f, names), f.value_text) for f in plan.facts)
    claim = re.search(r"(?:https?://|www\.)[^\s?]+|[a-z0-9-]+\.(?:com|org|net)(?:/[^\s?]*)?", plan.question or "", re.I)
    if claim:
        from .normalize import canonical_url
        asked = claim.group().rstrip(".,")
        asked = asked if asked.startswith("http") else "https://" + asked
        text = ("Yes. " if any(canonical_url(asked) == canonical_url(f.value_text) for f in plan.facts) else "No. ") + text
    return text


def render_how_to(plan: AnswerPlan) -> str:
    """A link as ``You can do that online at {url}``; any other row as in ``render_value``."""
    names = product_names()
    return "\n".join("You can do that online at {}".format(f.value_text) if f.attribute == "url"
                     else sentence("{}: {}".format(label(f, names), phrase((f,)))) for f in plan.facts)


def render_count(plan: AnswerPlan) -> str:
    """``{label}: {value_text}.``: what is counted, then the count as the site writes it."""
    return _table(plan)


def render_change(plan: AnswerPlan) -> str:
    """Rows paired across the two crawls by fact key. When the plan has two crawls and permits both dates, a header
    line ``Between {date A} and {date B}:`` dates them once and the rows read ``{label}: it was X; it is Y.``,
    ``{label}: unchanged at Y.``, or, for a row only one crawl has, ``it was X`` (the from-crawl) or ``it is Y``
    (the latest crawl). Otherwise each row dates itself: ``{label}: on {date A} it was X; on {date B} it is Y.``,
    ``{label}: unchanged at Y between {date A} and {date B}.``, ``{label}: on {date B} it is Y.``, with ``in an
    earlier crawl`` or ``in the latest crawl`` for a date the plan does not permit. A one-sided row is stated for
    its crawl alone, the other side never invented. The resolver's change plan holds the from-crawl's rows first,
    and ``plan.snapshot_id`` is the latest crawl."""
    names = product_names()
    by_key: Dict[FactKey, Dict[str, Row]] = {}
    for row in _rows(plan.facts):
        by_key.setdefault(row[0].key, {})[row[0].source.snapshot_id] = row
    days = [_date(sid, plan.permitted_values, True) for sid in dict.fromkeys(f.source.snapshot_id for f in plan.facts)]
    header = len(days) == 2 and all(days)
    lines = ["Between {} and {}:".format(*days)] if header else []
    for crawls in by_key.values():  # first appearance in the plan
        order = list(crawls)  # the from-crawl first
        old, new = crawls[order[0]], crawls[order[-1]]
        then, now = ("", "") if header else (_on(order[0], plan) + " ", _on(order[-1], plan) + " ")
        head = label(old[0], names)
        if len(order) == 1:
            if plan.same_crawl:
                dates = [_date(day, plan.permitted_values, True) for day in (plan.as_of, plan.as_of_end)]
                when = "{} and {}".format(*dates) if all(dates) else "the requested dates"
                lines.append(sentence("{}: unchanged at {} between {}".format(head, phrase(old), when)))
                continue
            verb = "is" if order[0] == plan.snapshot_id else "was"
            lines.append(sentence("{}: {}it {} {}".format(head, then, verb, phrase(old))))
        elif _values(old) == _values(new):
            dates = [_date(sid, plan.permitted_values, True) for sid in (order[0], order[-1])]
            between = " between {} and {}".format(*dates) if all(dates) and not header else ""
            lines.append(sentence("{}: unchanged at {}{}".format(head, phrase(new), between)))
        else:
            lines.append(sentence("{}: {}it was {}; {}it is {}".format(head, then, phrase(old), now, phrase(new))))
    return "\n".join(lines)


def render_past(plan: AnswerPlan) -> str:
    """A past-value plan (the resolver's ``PAST`` intent), rows paired by fact key. A key the reference crawl
    (``plan.snapshot_id``) lacks is an old value: ``{label}: {value} as of {Month D, YYYY}.``, dated by its own crawl.
    A key the reference crawl has never changed: ``{label}: unchanged at {value} since {Month D, YYYY}.``, the
    reference row's value dated by the key's first crawl in the plan (the first that carried it). A date the plan
    does not permit reads ``in an earlier crawl``, and the unchanged line leaves it out."""
    names = product_names()
    by_key: Dict[FactKey, Dict[str, Row]] = {}
    for row in _rows(plan.facts):
        by_key.setdefault(row[0].key, {})[row[0].source.snapshot_id] = row
    lines = []
    for crawls in by_key.values():
        first = next(iter(crawls))
        day = _date(first, plan.permitted_values, True)
        if plan.snapshot_id in crawls:
            row = crawls[plan.snapshot_id]
            since = " since " + day if day else ""
            lines.append(sentence("{}: unchanged at {}{}".format(label(row[0], names), phrase(row), since)))
        else:
            when = "as of " + day if day else "in an earlier crawl"
            lines.append(sentence("{}: {} {}".format(label(crawls[first][0], names), phrase(crawls[first]), when)))
    return "\n".join(lines)


def render_address(plan: AnswerPlan) -> str:
    """``The {branch} branch is at {address}.`` per fact."""
    return "\n".join(sentence("The {} branch is at {}".format(_branch(f), f.value_text) if _branch(f)
                               else "The address is {}".format(f.value_text)) for f in plan.facts)


def render_phone(plan: AnswerPlan) -> str:
    """``Call Dupaco at {number}.``, or the named branch's number."""
    return "\n".join(sentence("Call the {} branch at {}".format(_branch(f), f.value_text) if _branch(f)
                               else "Call Dupaco at {}".format(f.value_text)) for f in plan.facts)


def render_routing(plan: AnswerPlan) -> str:
    """``Dupaco's routing number is {number}.``"""
    return "\n".join(sentence("Dupaco's routing number is {}".format(f.value_text)) for f in plan.facts)


RENDERERS: Dict[str, Callable[[AnswerPlan], str]] = {
    "value": render_value, "list": render_list, "yes_no": render_yes_no, "url": render_url,
    "how_to": render_how_to, "status": render_status, "count": render_count, "change": render_change,
    "hours": render_hours, "address": render_address, "phone": render_phone, "routing": render_routing,
    PAST: render_past,
}
# A plan whose facts all hold one of these attributes renders by its template, whatever the intent, and undated: the
# alternatives of a closing branch answer a value question (Task 13).
_BY_ATTRIBUTE: Dict[str, Callable[[AnswerPlan], str]] = {"alternatives": render_alternatives}


def _by_attribute(plan: AnswerPlan) -> Optional[Callable[[AnswerPlan], str]]:
    """``_BY_ATTRIBUTE``'s template when every fact of the plan holds the one attribute it lists, else ``None``."""
    attribute = plan.facts[0].attribute if plan.facts else ""
    if (plan.intent in ("value", "count", "yes_no") and plan.facts
            and len({f.product_id for f in plan.facts}) == 1
            and all(f.attribute in ("description", "eligibility") for f in plan.facts)):
        return render_prose
    if attribute in _BY_ATTRIBUTE and all(f.attribute == attribute for f in plan.facts):
        return _BY_ATTRIBUTE[attribute]
    return None


def _before_first_crawl(plan: AnswerPlan) -> bool:
    """Whether ``plan.as_of`` precedes ``plan.first_crawl``, the earliest crawl's date (the resolver sets it)."""
    return bool(plan.as_of and plan.first_crawl and plan.as_of < plan.first_crawl)


def _crawl_covers(plan: AnswerPlan) -> bool:
    """Whether the plan's crawl stands for the month of ``plan.as_of``, on dates, never on the note: never for a date
    before the first crawl (``_before_first_crawl``: the earliest crawl stands in), and only up to the month of the
    crawl's own date (``plan.crawl_date``, else the one the snapshot id embeds), so a date after the last crawl never
    dates that crawl's facts. Months, as the prefix prints them: a mid-May date answered from the May 12 crawl keeps
    ``As of May 2026``."""
    crawl = _DATE_RE.search(plan.snapshot_id or "")
    day = plan.crawl_date or (crawl.group(0) if crawl else None)
    return day is not None and not _before_first_crawl(plan) and (plan.as_of or "")[:7] <= day[:7]


def _with_as_of(text: str, plan: AnswerPlan) -> str:
    """``As of May 2026, `` before the answer, after its verdict word when it opens with one, when the plan carries
    the date it answered against, permits its year and its crawl covers that month (``_crawl_covers``, checked
    before the verdict split); a change or past answer dates its own crawls, and an hours, status or ``_BY_ATTRIBUTE``
    answer carries no date."""
    when = _date(plan.as_of, plan.permitted_values, False)
    if when is None or plan.intent in _UNDATED or _by_attribute(plan) is not None or not _crawl_covers(plan):
        return text
    verdict = next((word for word in _VERDICTS if text.startswith(word)), "")
    return "{}As of {}, {}".format(verdict, when, text[len(verdict):])


def _cited(plan: AnswerPlan) -> List[AnswerSource]:
    """One source per distinct page of ``plan.sources``, first seen first: the resolver repeats a page once per
    fact, and the copies on other pages stay (the expected page may hold only a copy of the winning row)."""
    seen: Set[str] = set()
    out = []
    for s in plan.sources:
        if s.canonical_url not in seen:
            seen.add(s.canonical_url)
            out.append(AnswerSource(url=s.canonical_url, snapshot_id=s.snapshot_id, quote=s.quote))
    return out


def render_with_dropped(plan: AnswerPlan) -> Tuple[Answer, List[str]]:
    """``render``'s answer and the sentences its lint dropped (``explain`` shows them). An answer dated before the
    first crawl ends with the plan's note on its own line (the resolver's digit-free earliest-crawl sentence: User
    decision 1), added after the lint and the grounding check, so it neither grounds the answer nor adds a number."""
    if not plan.confident:
        if plan.withdrawn:
            head = label(plan.facts[0], product_names()) if plan.facts else "That"
            if not number_tokens(head) <= plan.permitted_values:
                head = "That"
            return Answer(text=head + " is no longer offered. Dupaco's website does not list a current value.",
                          sources=[], confident=False, conflict_note=plan.conflict_note), []
        return refusal(plan.refusal_span or _FALLBACK_SPAN), []
    template = _by_attribute(plan) or RENDERERS.get(plan.intent, render_value)
    text, dropped = lint(strip_residue(template(plan)), plan.permitted_values, strict=plan.strict_numbers)
    if not grounded(text, plan.facts):
        return refusal(plan.refusal_span or _FALLBACK_SPAN), dropped
    caveat = "\n" + plan.conflict_note if plan.conflict_note and _before_first_crawl(plan) else ""
    return Answer(text=_with_as_of(text, plan) + caveat, sources=_cited(plan), confident=True,
                  conflict_note=plan.conflict_note), dropped


def render(plan: AnswerPlan) -> Answer:
    """The member-facing answer for ``plan``: the refusal when the plan is not confident or the lint leaves no
    value, else the intent's template, residue-stripped and linted, with each distinct source page once and the
    plan's ``conflict_note``."""
    return render_with_dropped(plan)[0]
