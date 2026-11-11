"""Dated assertions (spec section 3a, row "5 temporal"): when an article was published, which dated facts hold at a
date, and a closure's status at a date.

``published_date`` reads a page's publication date from its header: the first of its first ``PUBLISHED_LINES`` (10)
lines, counted after a leading ``---`` front-matter block, that reads ``Month D, YYYY`` or is a legacy byline
``Written by [Name](url) \\| Mon D, YYYY h:mm:ss AM`` (``\\|`` or ``|``, a full or abbreviated month, an optional comma
after the year, an optional time; Task 6 ruling). ``article_body`` bounds the article on its page: from the H1 line
to the last line of the page's about tail, else to the line before the first ``## Handpicked for You``, ``## Recent
News`` (crawls 01-03) or ``[Keep reading]`` line, else to the page end, so related-article snippets and their
datelines stay out. ``kb.extract_prose`` reads both.

``select_dated`` picks, from a pool of facts that all carry a ``published_date``, the newest publication per fact key
up to a cutoff (``cutoff``: the asked date, tightened to the end of an asked year the facts do not carry), publication
over authority; ``status_at`` reads a closure as ``closed`` once its event date has passed. Stdlib only, no I/O.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from .blocks import Block
from .lexicon import MONTHS
from .store import _newest_first  # the store's exact descending order for date strings
from .types import Fact, FactKey

CLOSED, SCHEDULED = "closed", "scheduled"  # status_at's two readings

# The article header: "2 min read", the author, "July 23, 2021" (line 6 in most articles of crawls 01-02, so 6 lines
# left no slack), or a legacy byline under the H1 (line 5; line 6 after the front matter of crawl 05's two articles).
PUBLISHED_LINES = 10
_FRONT_MATTER = "---"  # a page opening with this line has a front-matter block, up to the next such line

# A publication date spells its month out: each month's longest name in lexicon.MONTHS ("september", never "sept"
# or "sep"), in month order. Fixed English names: calendar.month_name and strptime("%B") follow the locale.
_FULL_MONTHS = {number: name for name, number in sorted(MONTHS.items(), key=lambda item: (len(item[0]), item[0]))}
_MONTH_ALTERNATION = "|".join(name.title() for _, name in sorted(_FULL_MONTHS.items(), key=lambda item: item[0]))
_PUBLISHED_RE = re.compile(r"^(" + _MONTH_ALTERNATION + r")\s+(\d{1,2}),\s*(\d{4})$")
# A byline may abbreviate its month: any name lexicon.MONTHS knows ("sep", "sept") or a month's first three letters
# ("Apr": lexicon.MONTHS has no bare "apr", which a question means as the APR).
_MONTH_NUMBERS = {**{name[:3]: number for number, name in _FULL_MONTHS.items()}, **MONTHS}
_BYLINE_RE = re.compile(r"^Written by\s.*\|\s*("
                        + "|".join(name.title() for name in sorted(_MONTH_NUMBERS, key=lambda name: (-len(name), name)))
                        + r")\s+(\d{1,2}),\s*(\d{4}),?(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)?$")
_H1_RE = re.compile(r"^#\s+\S")
# The related-article list: "## Handpicked for You" (once "For"), "## Recent News" in crawls 01-03, or its links.
_RELATED_RE = re.compile(r"^(?:##\s+(?:handpicked for you|recent news)\b|\[keep reading\])", re.I)


def _header(markdown: str) -> List[str]:
    """The page's first ``PUBLISHED_LINES`` lines, counted from the line after the closing ``---`` when the page opens
    with a front-matter block (a first line ``---`` up to the next ``---`` line; one never closed is none)."""
    text = markdown or ""
    if text.split("\n", 1)[0].strip() == _FRONT_MATTER:
        lines = text.split("\n")
        close = next((i for i in range(1, len(lines)) if lines[i].strip() == _FRONT_MATTER), None)
        if close is not None:
            return lines[close + 1:close + 1 + PUBLISHED_LINES]
    return text.split("\n", PUBLISHED_LINES)[:PUBLISHED_LINES]


def _date_of(line: str) -> Optional[str]:
    """The ISO date a header line prints as ``Month D, YYYY`` or in a legacy byline; ``None`` for any other line and
    for a day the calendar lacks (``February 30, 2024``)."""
    text = line.strip()
    m = _PUBLISHED_RE.match(text) or _BYLINE_RE.match(text)
    if m is None:
        return None
    try:
        return date(int(m.group(3)), _MONTH_NUMBERS[m.group(1).lower()], int(m.group(2))).isoformat()
    except ValueError:
        return None


def published_date(markdown: str) -> Optional[str]:
    """The ISO date of the first header line (``_header``) that prints one (``_date_of``): ``April 06, 2026`` ->
    ``2026-04-06``, ``Written by [Name](url) \\| Sep 29, 2022 11:30:10 AM`` -> ``2022-09-29``; ``None`` when none
    does. A bare abbreviated month (``Sep 29, 2022``) is no publication date: only a byline abbreviates."""
    return next((day for day in (_date_of(line) for line in _header(markdown)) if day is not None), None)


def article_body(lines: Sequence[str], blocks: Sequence[Block]) -> Tuple[int, int]:
    """Inclusive 0-based line indices of the article: from the H1 line (the first line without one) to the last
    line of the first about tail at or below it; without a tail, to the line before the first ``## Handpicked for
    You``, ``## Recent News`` or ``[Keep reading]`` line below the H1, else to the page end. ``blocks`` are
    ``split_blocks`` of the same lines (1-based ``start_line``/``end_line``)."""
    start = next((i for i, line in enumerate(lines) if _H1_RE.match(line.strip())), 0)
    tail = next((b for b in blocks if b.kind == "about_tail" and b.start_line - 1 >= start), None)
    if tail is not None:
        return start, tail.end_line - 1
    related = next((i for i in range(start, len(lines)) if _RELATED_RE.match(lines[i].strip())), None)
    return start, (related if related is not None else len(lines)) - 1


def _dated_rank(f: Fact) -> Tuple:
    """Explicit sort key, the winner first: newest ``published_date``, then authority (descending), ``fetched_at``
    (descending), ``canonical_url`` (ascending), ``block_idx`` and ``row_idx``."""
    s = f.source
    return (_newest_first(f.published_date), -s.authority, _newest_first(s.fetched_at), s.canonical_url, s.block_idx,
            s.row_idx)


def select_dated(facts: Sequence[Fact], cutoff: Optional[str]) -> List[Fact]:
    """The facts in force at ``cutoff`` (an ISO date; ``None``: no cut) from a pool whose facts all carry a
    ``published_date``: those published after it are dropped (an undated one too, when there is a cut), then each
    fact key keeps its newest publication (``_dated_rank`` breaks ties), whatever the page's authority. The kept
    facts come in the order their keys first appear in ``facts``."""
    best: Dict[FactKey, Fact] = {}
    for f in facts:
        if cutoff is not None and (f.published_date is None or f.published_date > cutoff):
            continue
        held = best.get(f.key)
        if held is None or _dated_rank(f) < _dated_rank(held):
            best[f.key] = f  # a dict keeps a key where it was first inserted
    return list(best.values())


def status_at(f: Fact, reference: str) -> str:
    """``closed`` when the fact's ``event_date`` falls before ``reference`` (an ISO date), else ``scheduled``: on the
    event day itself, and for a fact without an event date, nothing has closed yet."""
    return CLOSED if f.event_date is not None and f.event_date < reference else SCHEDULED


def key_history(store, key: FactKey):
    """Every crawl, including absence, for one exact key in chronological order."""
    from .tiers import current
    out = []
    for sid, day in store.snapshots():
        pool = [f for f in store.in_force(sid, key[0], key[1], day) if f.key == key]
        ranked = select_dated(pool, day) if any(f.published_date for f in pool) else current(pool)
        out.append((sid, ranked[0] if ranked else None))
    return out


def cutoff(q_as_of: Optional[str], year: Optional[int], year_scoped: bool) -> Optional[str]:
    """The publication cutoff of a dated pool: ``q_as_of`` (the asked date, one before the first crawl included),
    tightened to ``YYYY-12-31`` when the question names a ``year`` that applies to publication, i.e. the pool's facts
    carry no ``year`` qualifier (``year_scoped`` False); with a ``year`` qualifier the year filters instead
    (``tiers.QUALIFIER_FILTERS["year"]``). ``None``: no cut."""
    if year is None or year_scoped:
        return q_as_of
    end = "%04d-12-31" % int(year)
    return end if q_as_of is None or end < q_as_of else q_as_of
