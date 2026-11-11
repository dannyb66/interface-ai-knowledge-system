"""Prose extractor: facts read from the body of a dated newsroom, blog or business-resource article.

``prose_facts`` reads a page only when its type is in ``PROSE_PAGE_TYPES`` (never a legacy alias, a contact page or
a product page) and it has a publication date (``kb.temporal.published_date``). The article body
(``kb.temporal.article_body``) runs from the H1 line to the last line of the page's about tail, else to the line
before the first ``## Handpicked for You``, ``## Recent News`` (crawls 01-03) or ``[Keep reading]`` line, else to the
page end, so related-article snippets and their datelines stay out. Both live in ``kb.temporal`` (Task 6) and are
imported back here.

Branch hours (``extract_hours``): after a body line ending ``Branch hours are:``, header lines (``**Lobby**``,
``**Drive-up**``, text after the header read as a day line) choose the attribute and day lines (``Monday-Thursday:
8:30 a.m.–5 p.m.``) give one fact each, blank lines skipped, up to the first line that is neither (the ``**ABOUT
DUPACO ...`` caption). A fact is product ``branch``, attribute ``lobby_hours`` or ``driveup_hours``, qualifiers
``branch_name`` (``branch_of``) and ``day`` (``day_label``), ``value_text`` the time exactly as printed and
``value`` None, an assertion carrying the article's publication date; its source is the page line (``block_idx``
-1, ``row_idx`` the 0-based line index, the raw line as the quote). The /contact page's reply hours are a contact
fact (``extract_rules``), never branch hours.

Closures (``extract_closures``): an article whose H1 is a closure headline (``_CLOSURE_H1_RE``: ``plans``, ``closing``,
``to close`` or ``will close`` before ``branch``, or ``branch closure``) names its branch there (``closure_branch``:
the capitalised words before ``branch``, ``norm_text``-ed: ``hy-vee``, ``asbury``). The first body line stating the
event (``will close`` or ``last day of service will be``, an optional weekday, then ``Month D, YYYY``) gives a
``closure_date`` fact: ``value_text`` the date as printed (``Oct. 1, 2024``), ``event_date`` its ISO date
(``normalize.parse_date``; a day the calendar lacks gives none), a status claim. The first body line, links reduced to
their text, saying members ``can access the same (or similar) services at`` Dupaco's ``full-service branch(es) at``
X gives an ``alternatives`` assertion, X up to the first comma, period, quote or dash. Both are product ``branch``
with the qualifier ``branch_name`` alone, carry the publication date and quote their line as the hours do. Standard
library only, no I/O.
"""
from __future__ import annotations

import re
from typing import FrozenSet, List, Optional, Sequence, Tuple

from .blocks import split_blocks
from .extract_rules import _LINK_RE, SourceContext  # _LINK_RE: a markdown link or image reduced to its text
from .normalize import norm_text, normalize_dashes, parse_date
from .temporal import article_body, published_date
from .types import ClaimType, Fact, make_key
from .article_facts import branch_contacts, counts as extract_counts

PROSE_PAGE_TYPES = frozenset({"newsroom", "blog", "business_resource"})
EXTRACTOR = "prose"
PROSE_CONFIDENCE = 1.0

_START_WORDS = "branch hours are"  # a cheap test before the line scan and the second block split
_START_RE = re.compile(r"(?i)\bbranch hours are:?\s*$")
_HEADER_RE = re.compile(r"^\*\*(Lobby|Drive-up|Drive-thru|Drive up)\*\*:?\s*(.*)$")
_DAY = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day"
_DAY_LINE_RE = re.compile(r"^(?P<days>" + _DAY + r"(?:\s*[-–—]\s*" + _DAY + r")?):\s*(?P<value>\S.*)$")
_DAY_LABEL_RE = re.compile(r"^(" + _DAY + r")(?:\s*-\s*(" + _DAY + r"))?$", re.I)
_CITY_RE = re.compile(r"^([A-Z][A-Za-z.' ]+),\s*(?:Iowa|IA|Wis\.|Wisconsin|WI|Ill\.|Illinois|IL)\s*[–—-]")
_NAME_RE = re.compile(r"(?i)phone number for the ([a-z][\w.' ]*?) branch\b")
_LOBBY = "Lobby"  # the lobby header; every other header is the drive-up
_H1_TEXT_RE = re.compile(r"^#\s+(\S.*)$")  # kb.temporal's H1 test, keeping the headline's text
_CLOSURE_H1_RE = re.compile(r"(?i)\b(?:plans|closing|to close|will close)\b.*\bbranch\b|\bbranch closure\b")
_CLOSING_BRANCH_RE = re.compile(r"([A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)\s+branch\b")  # case-sensitive: capitalised words
_EVENT_RE = re.compile(r"(?i)\b(?:will close|last day of service will be)\s+(?:on\s+)?(?:[A-Z][a-z]+day,\s+)?"
                       r"(?P<date>[A-Z][a-z]{2,8}\.?\s+\d{1,2},\s+\d{4})")
_ALTERNATIVES_RE = re.compile(r"(?i)can access (?:the same|similar) services at (?:a |the )?(?:Dupaco )?full-service "
                              r"branch(?:es)? at (?P<alt>.+?)(?=[,.”\"—–]|$)")


def day_label(text: str) -> Optional[str]:
    """A printed day or day range as a ``day`` qualifier: lowercased, dashes mapped, no spaces around the dash
    (``Monday-Thursday`` -> ``monday-thursday``, ``Monday–Friday`` -> ``monday-friday``); ``None`` for other text."""
    m = _DAY_LABEL_RE.match(normalize_dashes(text).strip())
    return None if m is None else "-".join(day.lower() for day in m.groups() if day)


def branch_of(lines: Sequence[str], body: Tuple[int, int]) -> Optional[str]:
    """The article's branch: ``"<name>, <city>"``, the city alone when there is no name or the name is the city,
    the name alone when there is no city, ``None`` when neither is found. The city opens the first body line of the
    form ``CITY, State–`` (``PLATTEVILLE, Wis.—``); the name is ``phone number for the <name> branch`` in a body line
    up to the first start line, the start line included (``The phone number for the East Washington branch is ...
    Branch hours are:``). Both are normalised (``norm_text``)."""
    lo, hi = body
    city = next((norm_text(m.group(1)) for m in (_CITY_RE.match(lines[i].strip()) for i in range(lo, hi + 1)) if m),
                None)
    start = next((i for i in range(lo, hi + 1) if _START_RE.search(lines[i])), hi)
    name = next((norm_text(m.group(1)) for m in (_NAME_RE.search(lines[i]) for i in range(lo, start + 1)) if m), None)
    if name and name != city:
        return "{}, {}".format(name, city) if city else name
    return city


def _hours_fact(ctx: SourceContext, attribute: str, branch: str, day: Optional[str], value_text: str, line_idx: int,
                quote: str, published: str) -> Fact:
    key = make_key("branch", attribute, {"branch_name": branch, "day": day})
    return Fact(key, "branch", attribute, key[2], None, value_text, "text", ClaimType.ASSERTION, None, None, published,
                ctx.source(-1, line_idx, quote), EXTRACTOR, PROSE_CONFIDENCE)


def _hours_block(lines: Sequence[str], start: int, hi: int, ctx: SourceContext, branch: str,
                 published: str) -> Tuple[List[Fact], int]:
    """The facts of the hours block after start line ``start`` and the index of the line that ended it (``hi + 1``
    at the body end). A day line before any header has no attribute and gives no fact."""
    facts: List[Fact] = []
    attribute: Optional[str] = None
    k = start + 1
    while k <= hi:
        text = lines[k].strip()
        header = _HEADER_RE.match(text)
        if header:
            attribute = "lobby_hours" if header.group(1) == _LOBBY else "driveup_hours"
            text = header.group(2).strip()
        day_line = _DAY_LINE_RE.match(text) if text else None
        if text and not header and day_line is None:
            break  # neither a header nor a day line: the block is over
        if day_line is not None and attribute is not None:
            facts.append(_hours_fact(ctx, attribute, branch, day_label(day_line.group("days")),
                                     day_line.group("value").strip(), k, lines[k], published))
        k += 1
    return facts, k


def extract_hours(lines: Sequence[str], body: Tuple[int, int], ctx: SourceContext, published: str) -> List[Fact]:
    """One fact per day line of every hours block in the body (see the module docstring), in page order; ``[]``
    when the article names no branch (``branch_of``)."""
    lo, hi = body
    branch = branch_of(lines, body)
    if branch is None:
        return []
    facts: List[Fact] = []
    i = lo
    while i <= hi:
        if _START_RE.search(lines[i]):
            block, i = _hours_block(lines, i, hi, ctx, branch, published)
            facts.extend(block)
        else:
            i += 1
    return facts


def _headline(line: str) -> Optional[str]:
    """The text of an H1 line (``# Dupaco closing Asbury branch ...``), else ``None``."""
    m = _H1_TEXT_RE.match(line.strip())
    return m.group(1) if m else None


def closure_branch(headline: Optional[str]) -> Optional[str]:
    """The branch a closure headline names (``plans Hy-Vee branch closure`` -> ``hy-vee``, ``Dupaco closing Asbury
    branch to ...`` -> ``asbury``); ``None`` for no headline, one that is no closure headline, or one naming no
    branch (``plans learning lab branch in Grimes``)."""
    if headline is None or not _CLOSURE_H1_RE.search(headline):
        return None
    m = _CLOSING_BRANCH_RE.search(headline)
    return norm_text(m.group(1)) if m else None


def _closure_fact(ctx: SourceContext, attribute: str, branch: str, value_text: str, event: Optional[str],
                  line_idx: int, quote: str, published: str) -> Fact:
    key = make_key("branch", attribute, {"branch_name": branch})
    claim = ClaimType.STATUS if attribute == "closure_date" else ClaimType.ASSERTION
    return Fact(key, "branch", attribute, key[2], None, value_text, "text", claim, None, event, published,
                ctx.source(-1, line_idx, quote), EXTRACTOR, PROSE_CONFIDENCE)


def _event(line: str) -> Optional[Tuple[str, str]]:
    """The first closure event ``line`` states, as ``(date as printed, ISO date)``; ``None`` if none has a real day."""
    for m in _EVENT_RE.finditer(line):
        day = parse_date(m.group("date"))
        if day is not None:
            return m.group("date"), day
    return None


def _alternatives(line: str) -> Optional[str]:
    """The branches ``line`` (links reduced to their text) offers instead of the closing one, else ``None``."""
    m = _ALTERNATIVES_RE.search(_LINK_RE.sub(r"\1", line))
    alt = m.group("alt").strip() if m else ""
    return alt or None


def extract_closures(lines: Sequence[str], body: Tuple[int, int], ctx: SourceContext, published: str) -> List[Fact]:
    """A closure article's ``closure_date`` fact, then its ``alternatives`` fact (see the module docstring), each from
    the first body line that states one; ``[]`` unless the body opens with a closure headline naming a branch."""
    lo, hi = body
    branch = closure_branch(_headline(lines[lo])) if lo < len(lines) else None
    if branch is None:
        return []
    closure: Optional[Fact] = None
    alternative: Optional[Fact] = None
    for i in range(lo, hi + 1):
        event = _event(lines[i]) if closure is None else None
        if event is not None:
            closure = _closure_fact(ctx, "closure_date", branch, event[0], event[1], i, lines[i], published)
        alt = _alternatives(lines[i]) if alternative is None else None
        if alt is not None:
            alternative = _closure_fact(ctx, "alternatives", branch, alt, None, i, lines[i], published)
    return [f for f in (closure, alternative) if f is not None]


def prose_facts(markdown: str, ctx: SourceContext, boilerplate: FrozenSet[str]) -> List[Fact]:
    """Every prose fact of one page: ``[]`` unless the page type is in ``PROSE_PAGE_TYPES`` and the page has a
    publication date, so a legacy alias is skipped; then the branch hours (``extract_hours``) and the closure facts
    (``extract_closures``) of the article body, hours first. Each reader runs only on a page that passes its cheap
    test (the hours start words; a first H1 that is a closure headline naming a branch), and the blocks are split
    once, only when one does: most articles state neither."""
    if ctx.page_type not in PROSE_PAGE_TYPES:
        return []
    published = published_date(markdown)
    if published is None:
        return []
    lines = [line.rstrip("\r") for line in markdown.split("\n")]  # split_blocks' own lines, so indices agree
    hours = _START_WORDS in markdown.lower()
    closing = closure_branch(next((h for h in map(_headline, lines) if h is not None), None)) is not None
    blocks = split_blocks(markdown, boilerplate)
    body = article_body(lines, blocks)
    return ((extract_hours(lines, body, ctx, published) if hours else [])
            + (extract_closures(lines, body, ctx, published) if closing else [])
            + extract_branch_contacts(lines, body, ctx, published)
            + extract_counts(lines, blocks, body, ctx, published))


def extract_branch_contacts(lines, body, ctx, published):
    return branch_contacts(lines, body, ctx, published, branch_of(lines, body))
