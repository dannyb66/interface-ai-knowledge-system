"""Prose answer templates (Phase 3): branch hours, closures and alternatives, and the branch names the composer prints.

``render_hours`` (``compose.RENDERERS["hours"]``) prints a plan's branch lobby or drive-up hours one line per
schedule (``schedules``): ``{Kind} at the {B} branch: {Day} {value}; {Day} {value}.``, or ``{Kind} at the {B1}, {B2}
and {B3} branches: ...`` for branches whose schedules are equal. The days keep the page's line order and the values
the surface form of the newest article; the lines run by branch count, then newest article, then name. Facts that
cover two or more branches, or a branch-hours fact naming none, end with ``HOURS_NOTE``; a question with the word
``same`` over two or more schedules opens with ``No. Hours vary by branch.``. A fact without a branch name keeps the
Phase 2 line, ``{Kind}: {value_text}.`` (``on {Day}`` after the kind when it has a day). Hours answers carry no date
(User decision 3: ``compose._with_as_of`` skips them), and no template prints the question, which is read for the
word ``same`` only.

``render_status`` (``compose.RENDERERS["status"]``, Task 13) reads each closure (a fact with an ``event_date``) at the
plan's reference date (``as_of``, else the answering crawl's date): ``The {B} branch closed on {date}.`` or ``The {B}
branch is scheduled to close on {date}.``, the date as the article prints it, opening with ``No.`` or ``Yes.`` only for
a yes/no question asking whether one branch is open (``_verdict``); a status fact without an event date keeps the
Phase 2 line, ``{label}: {value_text}.``. ``render_alternatives`` (dispatched by ``compose`` on the facts' attribute)
prints ``Members of the {B} branch can use Dupaco's full-service branches at {value_text}.``. Neither is dated
either: a closure prints its own date. ``branch_display`` names every branch the composer prints. Imports nothing
from ``kb.compose``, which imports these names (``HOURS_NOTE`` is re-exported there). Stdlib only.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .labels import label, phrase, product_names, sentence, title_words
from .lexicon import CLOSURE_DATE_WORDS
from .normalize import normalize_dashes
from .temporal import CLOSED, status_at
from .types import AnswerPlan, Fact
from .prose_verdict import prose_prefix

HOURS_NOTE = "Hours vary by branch; tell me which branch and I'll confirm."
VARY = "No. Hours vary by branch."  # the first line of a "same hours?" question over two or more schedules
HOURS_KINDS = {"lobby_hours": "Lobby hours", "driveup_hours": "Drive-up hours",
               "reply_hours": "Dupaco replies to messages"}
BRANCH_HOURS = frozenset({"lobby_hours", "driveup_hours"})  # the kinds a branch's schedule holds
_SAME_RE = re.compile(r"\bsame\b", re.I)
_ABBREVIATION_RE = re.compile(r"\.(?=\s|$)")  # the dot of "ln.": a ". " inside a label is where the lint splits
_CRAWL_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")  # the crawl date a snapshot id embeds (05_2026-09-28_latest)
_WORD_RE = re.compile(r"[a-z]+")
_VERDICT_LEADS = frozenset({"is", "are", "was", "were", "does", "do", "has", "will"})  # a yes/no question's first word
_OPEN = "open"  # the verdict answers "is it open?": "No." (closed) or "Yes." (scheduled)

Days = Tuple[Tuple[str, str], ...]  # ((day qualifier, value_text), ...) in the page's line order
Schedule = Tuple[Tuple[str, ...], Days]  # (branch display names, days)


def branch_display(name: str) -> str:
    """A stored branch name as the composer prints it: ``east washington, madison`` -> ``East Washington (Madison)``,
    ``platteville`` -> ``Platteville``. The dot ending an abbreviation goes (``Oldenburg Ln (Galena)``), so no label
    holds a ". " where the lint would split its sentence."""
    street, _, city = str(name).partition(", ")
    street, city = (title_words(_ABBREVIATION_RE.sub("", part.strip())) for part in (street, city))
    return "{} ({})".format(street, city) if city else street


def _name(f: Fact) -> Optional[str]:
    name = dict(f.qualifiers).get("branch_name")
    return str(name) if name else None


def _day(f: Fact) -> str:
    return str(dict(f.qualifiers).get("day") or "")


def schedules(facts: Sequence[Fact]) -> List[Schedule]:
    """The schedules of one kind's facts that name a branch, in print order. A branch's days keep the page's line
    order (``source.row_idx``, week order on every page; never the alphabetical order of ``tiers._tier_key``).
    Branches share an entry when their schedules are equal on ``(day, normalize_dashes(value).lower())``; it holds
    their display names in alphabetical order and the days of the newest article among them (``published_date``, the
    first name on a tie), so it prints that surface form. Entries run by the number of branches (descending), the
    newest publication date (descending), then the first name."""
    by_branch: Dict[str, List[Fact]] = {}
    for f in facts:
        if _name(f) is not None:
            by_branch.setdefault(branch_display(_name(f) or ""), []).append(f)
    shared: Dict[Days, List[Tuple[str, str, Days]]] = {}  # equal schedules -> [(name, newest date, days)]
    for name in sorted(by_branch):
        rows = sorted(by_branch[name], key=lambda f: (f.source.row_idx, _day(f), f.value_text))
        days = tuple((_day(f), f.value_text) for f in rows)
        shape = tuple((day, normalize_dashes(value).lower()) for day, value in days)
        shared.setdefault(shape, []).append((name, max(f.published_date or "" for f in rows), days))
    entries = []
    for members in shared.values():
        newest = max(date for _, date, _ in members)
        surface = next(days for _, date, days in members if date == newest)
        entries.append((tuple(name for name, _, _ in members), newest, surface))
    entries.sort(key=lambda e: e[0][0])  # stable sorts: the first name, under the newest date, under the count
    entries.sort(key=lambda e: e[1], reverse=True)
    entries.sort(key=lambda e: len(e[0]), reverse=True)
    return [(names, days) for names, _, days in entries]


def _line(kind: str, names: Tuple[str, ...], days: Days) -> str:
    where = names[0] + " branch" if len(names) == 1 else "{} and {} branches".format(", ".join(names[:-1]), names[-1])
    when = "; ".join("{} {}".format(title_words(day), value) if day else value for day, value in days)
    return sentence("{} at the {}: {}".format(HOURS_KINDS.get(kind, "Hours"), where, when))


def render_hours(plan: AnswerPlan) -> str:
    """One line per schedule of each kind, kinds in plan order; ``No. Hours vary by branch.`` first when the question
    says ``same`` and there are two or more; then each fact without a branch name as ``{Kind}: {value_text}.``; then
    ``HOURS_NOTE`` when the branch-hours facts cover two or more branches or one names none."""
    kinds = list(dict.fromkeys(f.attribute for f in plan.facts if _name(f) is not None))
    lines = [_line(kind, names, days) for kind in kinds
             for names, days in schedules([f for f in plan.facts if f.attribute == kind])]
    if len(lines) > 1 and _SAME_RE.search(plan.question or ""):
        lines.insert(0, VARY)
    for f in plan.facts:
        if _name(f) is None:  # the Phase 2 line
            head = HOURS_KINDS.get(f.attribute, "Hours") + (" on {}".format(title_words(_day(f))) if _day(f) else "")
            lines.append(sentence("{}: {}".format(head, f.value_text)))
    hours = [f for f in plan.facts if f.attribute in BRANCH_HOURS]
    if hours and (len({_name(f) for f in hours}) > 1 or _name(hours[0]) is None):
        lines.append(HOURS_NOTE)
    return "\n".join(lines)


def _branch_words(f: Fact) -> str:
    """``Hy-Vee branch`` for a fact naming its branch, else ``branch``."""
    name = _name(f)
    return "{} branch".format(branch_display(name)) if name else "branch"


def _reference(plan: AnswerPlan) -> str:
    """The date a closure's status is read at: ``plan.as_of``, else the answering crawl's ``plan.crawl_date``, else
    the date its snapshot id embeds (a plan built by hand); ``""`` without any: every closure then reads scheduled."""
    crawl = _CRAWL_DAY_RE.search(plan.snapshot_id or "")
    return plan.as_of or plan.crawl_date or (crawl.group(0) if crawl else "")


def _verdict(plan: AnswerPlan, closures: int) -> bool:
    """Whether the closure line opens with ``No.``/``Yes.``: the plan holds one closure and the question opens with a
    ``_VERDICT_LEADS`` word, asks the status rather than the date (no ``CLOSURE_DATE_WORDS`` word: the parser's own
    rule) and asks whether the branch is open (ruling: "Is the Asbury branch closed?" answered ``No.`` would
    contradict its line). The question is read, never printed."""
    words = _WORD_RE.findall((plan.question or "").lower())
    return (closures == 1 and bool(words) and words[0] in _VERDICT_LEADS and _OPEN in words
            and not CLOSURE_DATE_WORDS & set(words))


def render_status(plan: AnswerPlan) -> str:
    """One line per fact in plan order. A closure (a fact with an ``event_date``) read as closed at ``_reference``
    (``kb.temporal.status_at``: the event day itself is still scheduled) gives ``The {B} branch closed on {date}.``,
    else ``The {B} branch is scheduled to close on {date}.``, after ``No.`` or ``Yes.`` when ``_verdict`` holds; a
    status fact without an event date keeps the Phase 2 line, ``{label}: {value_text}.``."""
    reference = _reference(plan)
    verdict = _verdict(plan, sum(1 for f in plan.facts if f.event_date))
    lines = []
    for f in plan.facts:
        if not f.event_date:
            lines.append(sentence("{}: {}".format(label(f, product_names()), phrase((f,)))))
            continue
        closed = status_at(f, reference) == CLOSED
        when = "closed on" if closed else "is scheduled to close on"
        line = sentence("The {} {} {}".format(_branch_words(f), when, f.value_text))
        lines.append(("No. " if closed else "Yes. ") + line if verdict else line)
    return "\n".join(lines)


def render_alternatives(plan: AnswerPlan) -> str:
    """``Members of the {B} branch can use Dupaco's full-service branches at {value_text}.``, one line per fact."""
    return "\n".join(sentence("Members of the {} can use Dupaco's full-service branches at {}".format(
        _branch_words(f), f.value_text)) for f in plan.facts)


def render_prose(plan: AnswerPlan) -> str:
    """One product's verified sentences in their item order, with a yes/no verdict retained."""
    facts = sorted(plan.facts, key=lambda f: (dict(f.qualifiers).get("item", 0), f.source.row_idx, f.value_text))
    texts = list(dict.fromkeys(sentence(f.value_text) for f in facts))
    suffix = " eligibility" if facts[0].attribute == "eligibility" else ""
    text = "{}{}: {}".format(product_names().get(facts[0].product_id, facts[0].product_id), suffix, " ".join(texts))
    return prose_prefix(plan, product_names().get(facts[0].product_id, facts[0].product_id)) + text
