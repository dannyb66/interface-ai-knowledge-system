"""Rules extractor: table rows, inline rate sentences and ``/contact`` lines become ``Fact`` records.

Ported from ``docs/research/spikes/table_facts.py``: ``parse_table`` (lines 209-308) for table rows and
``parse_inline`` (lines 311-346, ``INLINE_RATE_RE`` verbatim) for inline rates. Departure from the spike: the
product never comes from a caption, a heading or the first label cell. A table row's product and label-derived
qualifiers come only from ``Registry.resolve``, and an inline rate needs a sentence that names exactly one
product through the registry's aliases.

- ``extract_block``: each table row the registry resolves yields one fact per non-empty value cell. The row's
  term, balance-tier, model-year and min/max-balance columns add qualifiers over the rule's, and header text
  tells duplicate column kinds apart (``... for 1st 6 Months`` columns carry ``intro=True``; ``... After
  Promotional Period`` columns are the standard rate). Rows the registry ignores or cannot resolve yield
  nothing: a never-seen row is appended to ``UNMAPPED``, a registry-ignored row only counted in ``IGNORED``.
- ``extract_inline``: ``x.xx% APY/APR`` phrases in prose sentences.
- ``extract_urls``: on a ``product_page``, one ``url`` fact per product whose table rows the page carries (value
  the page's canonical URL). A rate sheet carries every product's rows at the same authority, so its tables name
  no url, nor do the rate sheet's tab-widget tables a product page embeds (see ``extract_urls``).
- ``extract_contact``: the routing number (product ``membership``) on every page that states it, so each such
  page is a source; on ``contact`` pages also the phone and reply hours, one address per Dupaco branch in the
  locator and the locator page's own URL (product ``branch``).
- ``extract_join``: on /about/join only, the online application's link (product ``membership``, attribute ``url``).

Facts come out in page order, the url facts of the tables after the page's table and inline facts. Standard
library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Mapping, Match, Optional, Pattern, Sequence, Tuple

from .blocks import Block, Row, split_blocks, table_header, table_rows
from .normalize import (norm_text, parse_model_years, parse_money, parse_percent, parse_term_months, parse_tier,
                        strip_footnote)
from .pagetype import segment_of
from .registry import Registry
from .types import ClaimType, Fact, Source, make_key

EXTRACTOR = "rules"
TABLE_CONFIDENCE = 1.0
CONTACT_CONFIDENCE = 1.0
# A sentence names the product but rarely its tier, while a table row states the same rate with every
# qualifier. Store ranking ignores confidence; ``effective_date=None`` already ranks inline facts below
# dated table rows of the same authority.
INLINE_CONFIDENCE = 0.5

PERCENT_ATTRS = frozenset({"apy", "dividend_rate", "apr", "rate", "points"})
MONEY_ATTRS = frozenset({"payment_example", "min_to_open", "min_to_earn", "fee"})
RATE_ATTRS = frozenset({"apy", "dividend_rate", "apr", "rate"})  # ClaimType.RATE; all other attributes are assertions

# The ingest census line: (canonical_url, heading_path, row label) of every table row the registry has never
# seen (``resolve`` returned ``None``), and the number of rows an ignore entry matched. ``extract_block`` only
# adds to both; ``reset_census`` empties them (per snapshot).
UNMAPPED: List[Tuple[str, Tuple[str, ...], str]] = []
IGNORED: int = 0


def reset_census() -> None:
    """Empty ``UNMAPPED`` in place and zero ``IGNORED``."""
    global IGNORED
    UNMAPPED.clear()
    IGNORED = 0

INLINE_RATE_RE = re.compile(
    r"(\d+(?:\.\d+)?%\s*(?:[–-]\s*\d+(?:\.\d+)?%)?)\s*(?:intro(?:ductory)?\s+)?(APY|APR|annual percentage (?:yield|rate))",
    re.I,
)
_INTRO_WINDOW = (30, 40)  # characters searched for an intro marker before and after an inline match
# "for 1st 6 Months", "promotional", "intro"; "for 3 months" / "for 6 mos" after a rate is always a promotion here.
_INTRO_RE = re.compile(r"\b(?:1st|first)\s+\d+\s+months?\b|\bfor\s+(?:the\s+)?\d+\s+(?:months?|mos?)\b"
                       r"|\bpromo(?:tional)?\b|\bintro(?:ductory)?\b", re.I)
_AFTER_INTRO_RE = re.compile(r"\bafter\s+(?:the\s+)?(?:promo(?:tional)?|intro(?:ductory)?)\b", re.I)
_MIN_BALANCE_RE = re.compile(r"\bmin(?:imum)?\b\.?\s*balance\b", re.I)
_MAX_BALANCE_RE = re.compile(r"\bmax(?:imum)?\b\.?\s*balance\b", re.I)
_EMPTY_CELLS = frozenset({"", "—", "–", "-"})
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“'‘\[*_\\])")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_SEGMENT_MARK_RE = re.compile(r"\(business\)|\bbusiness\b")  # in normalised aliases

_DAY = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
_TIME = r"\d{1,2}(?::\d{2})?\s*[ap]\.?\s?m\.?"
_REPLY_RE = re.compile(r"\breply\s+(" + _DAY + r"\s*[–—-]\s*" + _DAY + r",?\s*" + _TIME + r"\s*[–—-]\s*" + _TIME + ")",
                       re.I)
# "Routing Number:** 273974581", "routing number (273974581)": only spaces, punctuation or brackets in between.
_ROUTING_RE = re.compile(r"\brouting number\b[\s:,*_#()\[\]–—-]*(\d{9})\b", re.I)
_PHONE_RE = re.compile(r"\bphone\b[\s:*]*\[?(\(?\d{3}\)?[-.\s]?\d{3}[-.]\d{4})\b", re.I)
_CONTACT_LINES = (("routing_number", _ROUTING_RE), ("phone", _PHONE_RE), ("reply_hours", _REPLY_RE))
_EVERY_PAGE = frozenset({"routing_number"})  # read on any page type; the other contact lines on contact pages only
_HEADING_RE = re.compile(r"^#{1,6}\s")
# "3299 Hillcrest Rd., Dubuque, IA, 52001": the street after its house number, the city, state and ZIP.
_ADDRESS_RE = re.compile(r"^\d+[A-Za-z]?\s+(.+?),\s*([A-Za-z][A-Za-z .'-]*),\s*[A-Z]{2},?\s*\d{5}(?:-\d{4})?$")
_BRANCH_TYPE_RE = re.compile(r"^dupaco branch$", re.I)
_SECTION_RE = re.compile(r"^#{1,2}\s+(.+?)\s*$")  # a level-1 or level-2 heading: "## Find a Location Near You"
# The rate sheets' tab widget (/rates and /business-rates in crawls 01-04), by its heading after norm_text.
_RATE_WIDGET_RE = re.compile(r"^select an option below:?$")
_JOIN_PAGE = "https://www.dupaco.com/about/join"
_JOIN_LINK_RE = re.compile(r"\]\((https?://join\.dupaco\.com/?)\)")  # the application's root, not "/login"


@dataclass(frozen=True)
class SourceContext:
    """The page a fact comes from: every ``Source`` field except the position and the quote."""

    url: str
    canonical_url: str
    page_type: str
    authority: int
    snapshot_id: str
    fetched_at: str

    def source(self, block_idx: int, row_idx: int, quote: str) -> Source:
        return Source(self.url, self.canonical_url, self.page_type, self.authority, self.snapshot_id,
                      self.fetched_at, block_idx, row_idx, quote)


def _fact(ctx: SourceContext, product_id: str, attribute: str, qualifiers: Mapping[str, Any],
          value: Optional[float], value_text: str, unit: str, effective_date: Optional[str],
          position: Tuple[int, int], quote: str, confidence: float) -> Fact:
    key = make_key(product_id, attribute, qualifiers)
    claim = ClaimType.RATE if attribute in RATE_ATTRS else ClaimType.ASSERTION
    return Fact(key, product_id, attribute, key[2], value, value_text, unit, claim, effective_date, None, None,
                ctx.source(position[0], position[1], quote), EXTRACTOR, confidence)


def _is_intro(text: str) -> bool:
    """A promotional-period marker (``for 1st 6 Months``, ``for 3 months``, ``promotional``, ``introductory``)
    that is not the period after the promotion (``After Promotional Period`` is the standard rate)."""
    return bool(_INTRO_RE.search(_AFTER_INTRO_RE.sub(" ", text)))


def _put(out: Dict[str, Any], name: str, value: Any) -> None:
    if value is not None:  # an open tier end or an unparsed cell adds nothing
        out[name] = value


def _column_qualifiers(row: Row, header: Sequence[str]) -> Dict[str, Any]:
    """Qualifiers read from the row's own tier columns. ``amount`` columns count only under a ``Min. Balance``
    or ``Max. Balance`` header (Launchpad on /personal/retirement); other amounts name no qualifier."""
    out: Dict[str, Any] = {}
    for i, (kind, cell) in enumerate(zip(row.columns, row.cells)):
        if kind == "term":
            _put(out, "term_months", parse_term_months(cell))
        elif kind == "balance_tier":
            low, high = parse_tier(cell)
            _put(out, "balance_min", low)
            _put(out, "balance_max", high)
        elif kind == "model_year":
            years = parse_model_years(cell)
            if years:
                out["model_year_min"], out["model_year_max"] = years
        elif kind == "amount":
            head = header[i] if i < len(header) else ""
            if _MIN_BALANCE_RE.search(head):
                _put(out, "balance_min", parse_money(cell))
            elif _MAX_BALANCE_RE.search(head):
                _put(out, "balance_max", parse_money(cell))
    return out


def _cell_value(attribute: str, cell: str) -> Optional[Tuple[Optional[float], str, str]]:
    """``(value, value_text, unit)`` of a value cell, ``None`` for an empty or dash cell. The value is the
    first number (a range keeps its full text); a cell without one (``N/A``, ``None``) stays as text."""
    text = strip_footnote(cell)
    text = re.sub(r"(?<=\.)\s+\d{1,2}$", "", text)
    if text in _EMPTY_CELLS:
        return None
    if attribute in PERCENT_ATTRS:
        value, unit = parse_percent(text), "pct"
    else:
        value, unit = parse_money(text), "usd"
    return (value, text, unit) if value is not None else (None, text, "text")


def extract_block(block: Block, ctx: SourceContext, registry: Registry) -> List[Fact]:
    """Facts of one table block, in row then column order; ``[]`` for a prose block or a header-less table.

    Each row resolves through ``registry.resolve`` (an empty label reaches the section-keyed rules); a row it
    cannot resolve yields nothing and goes to ``UNMAPPED``, a row it ignores yields nothing and adds one to
    ``IGNORED``. A deposit row with both a ``Dividend Rate`` and an ``APY`` column yields both facts, a
    mortgage row its rate, points, APR and payment example.
    """
    global IGNORED
    rows = table_rows(block)
    if not rows:
        return []
    header = table_header(block)
    segment = segment_of(ctx.canonical_url, block.heading_path)
    facts: List[Fact] = []
    for row in rows:
        res = registry.resolve(ctx.canonical_url, block.heading_path, row.label, segment)
        if res is None:
            UNMAPPED.append((ctx.canonical_url, block.heading_path, row.label))
            continue
        if res.ignored or res.product_id is None:
            IGNORED += 1
            continue
        qualifiers = dict(res.qualifiers)
        qualifiers.update(_column_qualifiers(row, header))
        for i, (kind, cell) in enumerate(zip(row.columns, row.cells)):
            if kind not in PERCENT_ATTRS and kind not in MONEY_ATTRS:
                continue
            parsed = _cell_value(kind, cell)
            if parsed is None:
                continue
            own = dict(qualifiers)
            if i < len(header) and _is_intro(header[i]):
                own["intro"] = True
            value, text, unit = parsed
            facts.append(_fact(ctx, res.product_id, kind, own, value, text, unit, block.effective_date,
                               (block.idx, row.row_idx), row.raw, TABLE_CONFIDENCE))
    return facts


def _sentence_spans(line: str) -> List[Tuple[int, int]]:
    """``(start, end)`` of each sentence: a break after ``.``, ``!`` or ``?`` and spaces, before a capital,
    quote, bracket or emphasis mark (so ``4.10%`` and ``a.m.–5:30`` never break)."""
    spans: List[Tuple[int, int]] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(line):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(line)))
    return [(a, b) for a, b in spans if line[a:b].strip()]


@lru_cache(maxsize=4)
def _alias_index(aliases: Tuple[Tuple[str, str], ...]) -> Tuple[Pattern[str], FrozenSet[str]]:
    """One alternation over every alias, longest first, so each position takes its longest alias
    (``business share savings`` before ``share savings``), and the family words among the aliases.

    A family word is a whole-word part of another product's alias (``mortgage`` in ``mortgage rate relief``,
    ``home loan`` in ``home loan refinance``): it names a family, not a product. A business twin is no
    evidence (``business platinum visa card`` minus ``business`` is ``platinum visa card``, the same product).
    """
    owner = dict(aliases)
    names = sorted(owner, key=lambda a: (-len(a), a))
    family = set()
    for alias in names:
        word = re.compile(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])")
        for other in names:
            if owner[other] != owner[alias] and word.search(other):
                twin = " ".join(_SEGMENT_MARK_RE.sub(" ", other).split())
                if owner.get(twin) != owner[alias]:
                    family.add(alias)
                    break
    matcher = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(a) for a in names) + r")(?![a-z])")
    return matcher, frozenset(family)


def _named_products(text: str, registry: Registry) -> FrozenSet[str]:
    """Ids of the products named in ``text`` (markdown links reduced to their text) by an alias that is not a
    family word."""
    aliases = registry.aliases()
    if not aliases:
        return frozenset()
    matcher, family = _alias_index(tuple(sorted(aliases.items())))
    clean = norm_text(_LINK_RE.sub(r"\1", text).replace("\\", ""))
    return frozenset(aliases[m.group(0)] for m in matcher.finditer(clean) if m.group(0) not in family)


def extract_inline(block: Block, ctx: SourceContext, registry: Registry) -> List[Fact]:
    """``x.xx% APY/APR`` phrases in the sentences of a prose block (``[]`` for any other block).

    A sentence counts only when it names exactly one product (family words such as "mortgage" name none: a
    HELOC disclosure about "total mortgage balances" is not a mortgage rate) whose published attributes
    include the rate, and, when the block's headings name products, one of those. Anything else is skipped,
    never guessed. ``intro=True`` when an intro marker sits within ``_INTRO_WINDOW`` of the phrase;
    ``row_idx`` is the sentence's position in the block.
    """
    if block.kind != "prose":
        return []
    facts: List[Fact] = []
    in_headings: Optional[FrozenSet[str]] = None
    ordinal = -1
    for line in block.lines:
        for start, end in _sentence_spans(line):
            ordinal += 1
            sentence = line[start:end].strip()
            matches = list(INLINE_RATE_RE.finditer(sentence))
            named = _named_products(sentence, registry) if matches else frozenset()
            if len(named) != 1:
                continue
            (product_id,) = tuple(named)
            if in_headings is None:
                in_headings = frozenset().union(*(_named_products(h, registry) for h in block.heading_path))
            if in_headings and product_id not in in_headings:
                continue
            published = registry.published(product_id)
            for m in matches:
                attribute = "apy" if re.search(r"apy|yield", m.group(2), re.I) else "apr"
                if attribute not in published:
                    continue
                window = sentence[max(0, m.start() - _INTRO_WINDOW[0]):m.end() + _INTRO_WINDOW[1]]
                qualifiers = {"intro": True} if _is_intro(window) else {}
                facts.append(_fact(ctx, product_id, attribute, qualifiers, parse_percent(m.group(1)),
                                   strip_footnote(m.group(0)), "pct", block.effective_date,
                                   (block.idx, ordinal), sentence, INLINE_CONFIDENCE))
    return facts


def extract_urls(tables: Sequence[Tuple[Block, Sequence[Fact]]], ctx: SourceContext, registry: Optional[Registry] = None) -> List[Fact]:
    """One ``url`` fact per product whose rows the table blocks of a ``product_page`` carry, in the order the
    products first appear (``[]`` for any other page type): value_text the page's canonical URL, no qualifiers,
    read from the product's newest table on the page (its effective date and position, the first such table on a
    tie), with that table's caption, its last heading (``Regular Certificates``), as the quote.

    The rate sheets (/rates, /business-rates) carry every product's rows at the same authority and are typed
    ``rate_sheet``, so they name no url. The one rule beyond the page type: a table under the rate sheets' tab
    widget heading (``Select an option below:``) names no url either, on whatever page embeds it. Crawls 01-04 copy
    the whole widget onto /personal/checking-accounts, so that page would otherwise be the only link for the
    personal Visas and the best-dated one for the personal, home-equity and home-improvement loans.
    """
    if ctx.page_type != "product_page":
        return []
    newest: Dict[str, Block] = {}  # product -> its newest table; insertion order is first appearance
    for block, facts in tables:
        if any(_RATE_WIDGET_RE.match(norm_text(h)) for h in block.heading_path):
            continue
        for f in facts:
            if registry is not None and registry.page(f.product_id):
                continue
            held = newest.get(f.product_id)
            if held is None or (block.effective_date or "") > (held.effective_date or ""):
                newest[f.product_id] = block
    return [_fact(ctx, pid, "url", {}, None, ctx.canonical_url, "text", block.effective_date, (block.idx, -1),
                  block.heading_path[-1] if block.heading_path else block.lines[0], TABLE_CONFIDENCE)
            for pid, block in newest.items()]


def _sentence_at(line: str, m: Match[str]) -> str:
    """The sentence of ``line`` holding the whole match, else the line."""
    for a, b in _sentence_spans(line):
        if a <= m.start() and m.end() <= b:
            return line[a:b].strip()
    return line


def _branch_addresses(lines: Sequence[str]) -> List[Tuple[int, str]]:
    """``(line index, address line)`` of each locator entry (a heading, then a type line, then an address
    line) whose type line reads ``Dupaco Branch``. ATM and shared-branch entries are not branches."""
    out: List[Tuple[int, str]] = []
    in_entry, entry_type = False, None
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if _HEADING_RE.match(line):
            in_entry, entry_type = True, None
        elif in_entry and entry_type is None:
            entry_type = line
        elif in_entry:
            if _ADDRESS_RE.match(line) and _BRANCH_TYPE_RE.match(entry_type or ""):
                out.append((i, line))
            in_entry = False
    return out


def _section_above(lines: Sequence[str], i: int) -> str:
    """The text of the nearest level-1 or level-2 heading above line ``i``, else line ``i`` itself."""
    for raw in reversed(lines[:i]):
        m = _SECTION_RE.match(raw.strip())
        if m:
            return m.group(1)
    return lines[i].strip()


def extract_contact(markdown: str, ctx: SourceContext) -> List[Fact]:
    """Contact facts of a page, all assertions with ``value=None`` and the verbatim text: the first routing number
    of any page (``routing number``, then the 9-digit value with only spaces, punctuation or brackets between);
    on a ``contact`` page also the first phone and reply hours (product ``membership``), then one ``address`` per
    Dupaco branch (product ``branch``, qualifier ``branch_name`` = the street without its house number and the
    city, normalised: ``oldenburg ln., galena``) and, when it lists any branch, the page's canonical URL as the
    branch ``url`` (the branch and ATM locator), quoting the locator's section heading.

    The quote is the sentence holding the match, or for the phone its line. These facts come from page lines, not
    blocks: ``block_idx`` is -1 and ``row_idx`` the 0-based line index (the first branch's for the url).
    """
    contact = ctx.page_type == "contact"
    if not contact and _ROUTING_RE.search(markdown or "") is None:
        return []  # the common case, without a walk over the lines
    lines = (markdown or "").split("\n")
    facts: List[Fact] = []
    found = set()
    for i, raw in enumerate(lines):
        line = raw.strip()
        for attribute, rx in _CONTACT_LINES:
            m = None if attribute in found or not (contact or attribute in _EVERY_PAGE) else rx.search(line)
            if m is None:
                continue
            found.add(attribute)
            quote = line if attribute == "phone" else _sentence_at(line, m)
            facts.append(_fact(ctx, "membership", attribute, {}, None, m.group(1), "text", None, (-1, i), quote,
                               CONTACT_CONFIDENCE))
    if not contact:
        return facts
    branches = _branch_addresses(lines)
    for i, address in branches:
        m = _ADDRESS_RE.match(address)
        name = norm_text("{}, {}".format(m.group(1), m.group(2))) if m else norm_text(address)
        facts.append(_fact(ctx, "branch", "address", {"branch_name": name}, None, address, "text", None, (-1, i),
                           address, CONTACT_CONFIDENCE))
    if branches:
        first = branches[0][0]
        facts.append(_fact(ctx, "branch", "url", {}, None, ctx.canonical_url, "text", None, (-1, first),
                           _section_above(lines, first), CONTACT_CONFIDENCE))
    return facts


def extract_join(markdown: str, ctx: SourceContext) -> List[Fact]:
    """The ``membership`` url, on the /about/join page only (``[]`` elsewhere, a legacy copy included): the first
    link to the root of join.dupaco.com, the online application, as written; ``/login`` resumes one, a product
    path (``/product/savingsAssetBuilder`` on the savings page) opens one account, and the home page's "Join
    Dupaco" points at /about/join itself. The quote is the link's line."""
    if ctx.canonical_url != _JOIN_PAGE or ctx.page_type == "legacy_alias":
        return []
    for i, raw in enumerate((markdown or "").split("\n")):
        m = _JOIN_LINK_RE.search(raw)
        if m:
            return [_fact(ctx, "membership", "url", {}, None, m.group(1), "text", None, (-1, i), raw.strip(),
                          CONTACT_CONFIDENCE)]
    return []


def extract_page(markdown: str, ctx: SourceContext, registry: Registry, boilerplate: FrozenSet[str]) -> List[Fact]:
    """Every rules fact of one page: table rows and inline rates block by block, the url facts of a product page's
    tables, then the contact facts and the join link."""
    facts: List[Fact] = []
    tables: List[Tuple[Block, List[Fact]]] = []
    for block in split_blocks(markdown, boilerplate):
        if block.kind == "table":
            rows = extract_block(block, ctx, registry)
            facts.extend(rows)
            tables.append((block, rows))
        elif block.kind == "prose":
            facts.extend(extract_inline(block, ctx, registry))
    facts.extend(extract_urls(tables, ctx, registry))
    facts.extend(extract_contact(markdown, ctx))
    facts.extend(extract_join(markdown, ctx))
    return facts
