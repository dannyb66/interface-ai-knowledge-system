"""Split page markdown into table, prose and about-tail blocks, and parse table rows.

Ported from ``docs/research/spikes/table_facts.py``: the heading/label fallback (lines 146-169) and the
header inference (lines 177-206). Departures from the spike are listed in ``infer_columns`` and
``_heading_paths``. Line numbers are 1-based and inclusive; ``Block.lines`` holds the block's non-empty
lines, stripped. A table's trailer need not be contiguous, so prose blocks can sit inside a table's line range.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, List, Optional, Sequence, Set, Tuple

from .config import DEFAULT_DATA_DIR
from .normalize import MODEL_YEAR_RE, MONEY_RE, PCT_RE, TERM_RE, parse_date, strip_footnote

ABOUT_MARKER = "About Dupaco"  # boilerplate.json carries it; split_blocks starts an about_tail on it
RATE_LIKE = frozenset({"apy", "dividend_rate", "apr", "rate", "points", "payment_example", "min_to_open",
                       "min_to_earn", "fee", "amount"})
TRAILER_CAP = 6  # non-empty lines scanned after a table, for its effective date and for its footnotes

SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
HEADING_RE = re.compile(r"^(#{1,6})(?:\s+(.*?))?\s*$")
# "effective" as a word, not inside "cost-effective"; matches "Rates are effective as of", "Rates
# effective 01/01/2023" and the PDF form "Effective February 17, 2025".
EFFECTIVE_LINE_RE = re.compile(r"(?<![\w-])effective\b", re.I)
# A footnote marker, after an optional bold or italic opener: one or two digits glued to a capital or followed by
# a period or spaces and a capital ("1Fixed Jumbo ...", "1 Boat & RV Loan Rates: ...", "2. Rates ..."), or an
# escaped or bare asterisk that does not open bold ("\*Payment example ...", "\*\*\*Mortgage ...", "*If
# applicable."). Not markers: "1st Rate Checking", "48 months", "5 steps to ...", "**Boat & RV loan ...**".
_FOOTNOTE_RE = re.compile(r"^(?:\*\*|_{1,2})?(?:\d{1,2}(?:\\?\.)?\s*[A-Z]|\\\*|\*(?!\*))")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“'‘\[*_\\])")  # extract_rules' break: "4.10%", "Sept. 1" stay
# The other effective-date cue: "as of" right before a date ("As of, 8/24/26", "as of September 1, 2026"; parse_date
# validates it) in a sentence with a rate word, edged by non-letters ("APY1" counts, "accurate" does not), but not
# a title-case Rate/Rates right after a capitalised word: a name ("FHLB Mortgage Rate Relief"), see _rate_word.
_AS_OF_DATE_RE = re.compile(r"(?<![\w-])as of[\s,:]+(\d{1,2}/\d{1,2}/\d{2,4}"
                            r"|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})", re.I)
_RATE_WORD_RE = re.compile(r"(?<![A-Za-z])(?:rates?|apy|apr|dividends?|yield)(?![A-Za-z])", re.I)
_NAME_WORD_RE = re.compile(r"[A-Z][\w'’&-]*")  # a capitalised word with no clause punctuation after it ("CST," is none)
# A date after one of these words ends an offer and never starts a rate: "Rates effective immediately, offer valid
# through 12/31/2026" has no effective date.
_END_WORD_RE = re.compile(r"(?<![\w-])(?:through|until|expires?|valid)(?![\w-])", re.I)
_HR_RE = re.compile(r"^(?:[-*_]\s*){3,}$")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_EMPTY_CELLS = frozenset({"", "—", "–", "-"})
_DATA_CELL_RE = re.compile(r"\d\s*%|\$\s?\d")  # a header cell holding a rate or an amount is a data row

ATTR_BY_HEADER = [
    (re.compile(r"dividend rate", re.I), "dividend_rate"),
    (re.compile(r"annual percentage yield|\bAPY\b", re.I), "apy"),
    (re.compile(r"annual percentage rate|\bAPR\b", re.I), "apr"),
    (re.compile(r"^\s*rate\b", re.I), "rate"),
    (re.compile(r"points", re.I), "points"),
    (re.compile(r"payment example", re.I), "payment_example"),
    (re.compile(r"min\.? to open", re.I), "min_to_open"),
    (re.compile(r"min\.? to earn", re.I), "min_to_earn"),
    (re.compile(r"fee", re.I), "fee"),
]
BALANCE_HEADER_RE = re.compile(r"^balance(?:\s+tier)?$", re.I)
LABEL_HEADERS = re.compile(
    r"account type|certificate|ira type|loan program|loan type|loan amount|card type|product|program|^term$|category",
    re.I,
)
_APR_CELL_RE = re.compile(r"\d+(?:\.\d+)?%\s*APR", re.I)
_APY_CELL_RE = re.compile(r"\d+(?:\.\d+)?%\s*APY", re.I)
_MODEL_YEAR_CELL_RE = re.compile(r"model year|\d{4}\s*[–-]\s*\d{2}", re.I)


@dataclass(frozen=True)
class Block:
    kind: str
    idx: int
    start_line: int
    end_line: int
    heading_path: Tuple[str, ...]
    lines: Tuple[str, ...]
    effective_date: Optional[str]
    footnotes: Tuple[str, ...]


@dataclass(frozen=True)
class Row:
    label: str
    cells: Tuple[str, ...]
    columns: Tuple[Optional[str], ...]
    row_idx: int
    raw: str


@lru_cache(maxsize=1)
def load_boilerplate() -> FrozenSet[str]:
    """The frozen ``lines`` of ``data/boilerplate.json`` (built by scripts/build_boilerplate.py)."""
    data = json.loads((DEFAULT_DATA_DIR / "boilerplate.json").read_text(encoding="utf-8"))
    return frozenset(data["lines"])


def _is_about_marker(stripped: str) -> bool:
    return re.sub(r"^[*_\s]+", "", stripped).casefold().startswith(ABOUT_MARKER.casefold())


def _line_kind(line: str, boilerplate: FrozenSet[str], tail_on: bool) -> str:
    s = line.strip()
    if not s or _HR_RE.match(s):
        return "blank"
    if s.startswith("|"):
        return "table"
    if HEADING_RE.match(s):
        return "heading"
    if tail_on and _is_about_marker(s):
        return "about"
    return "boiler" if s in boilerplate else "text"


def _heading_text(raw: str) -> str:
    t = _LINK_RE.sub(r"\1", raw).replace("\\|", "|").replace("\\#", "#").replace("\\*", "*")
    return re.sub(r"\s+#+$", "", t).strip().strip("*_").strip()


def _is_footnote(stripped: str) -> bool:
    return bool(_FOOTNOTE_RE.match(stripped))


def _is_label(stripped: str) -> bool:
    """The spike's short plain caption line (``Special Certificates`` on /rates, which has no # headings). Never a
    footnote line: ``\\*Business accounts are excluded`` under one table must not caption the next one."""
    s = stripped
    return (not s.startswith(("|", "[", "✕", "-", "*", "•", "!", "_")) and len(s) < 60
            and re.search(r"[A-Za-z]{3}", s) is not None and not s.endswith(".")
            and not EFFECTIVE_LINE_RE.search(s) and not _is_footnote(s))


def _heading_paths(lines: Sequence[str], kinds: Sequence[str]) -> List[Tuple[str, ...]]:
    """Heading path in force before each line: the open ``#`` headings plus the nearest caption line.

    Same result as the spike's upward walk, computed in one forward pass. Departures: empty headings
    (``###``) are skipped, and the caption must sit below the nearest heading with no table line between
    it and the block, so a caption never leaks into the next section or onto the next table.
    """
    out: List[Tuple[str, ...]] = []
    stack: List[Tuple[int, str]] = []
    label: Optional[str] = None
    for line, kind in zip(lines, kinds):
        heads = tuple(text for _, text in stack)
        out.append(heads + (label,) if label and (not heads or heads[-1] != label) else heads)
        if kind == "heading":
            m = HEADING_RE.match(line.strip())
            text = _heading_text(m.group(2) or "") if m else ""
            if text:
                level = len(m.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                label = None
        elif kind == "table":
            label = None
        elif kind == "text" and _is_label(line.strip()):
            label = line.strip().strip("*")
    return out


def _trailer(lines: Sequence[str], kinds: Sequence[str], start: int) -> Tuple[List[int], int]:
    """Indexes of the lines after a table that belong to it, and where the scan stopped.

    The scan reads the following non-empty lines, across blank lines, up to the first blank line after a line
    with the word ``effective`` and at most ``TRAILER_CAP`` of them (an ``as of`` cue line ends nothing, so an
    effective line below it is still read); it never crosses the next table, a heading or an about tail, and
    boilerplate lines count as blank. It picks only the date-cue lines (``_is_date_cue``) and footnote lines it
    reads; every other line stays prose. Nothing above the table is searched.
    """
    picked: List[int] = []
    scanned, seen_effective = 0, False
    k = start
    while k < len(lines) and scanned < TRAILER_CAP:
        kind = kinds[k]
        if kind in ("table", "heading", "about"):
            break
        if kind in ("blank", "boiler"):
            if seen_effective:
                break
        else:
            scanned += 1
            if _is_date_cue(lines[k]) or _is_footnote(lines[k].strip()):
                picked.append(k)
            seen_effective = seen_effective or bool(EFFECTIVE_LINE_RE.search(lines[k]))
        k += 1
    return picked, k


def _footnotes(lines: Sequence[str], kinds: Sequence[str], trailer: List[int], stop: int) -> Tuple[str, ...]:
    """Distinct footnote-marked lines in the trailer and in the next ``TRAILER_CAP`` non-empty lines before
    another table, heading or about tail. Every footnote line also stays in its prose block."""
    notes = [lines[k].strip() for k in trailer if _is_footnote(lines[k].strip())]
    seen, k = 0, stop
    while k < len(lines) and seen < TRAILER_CAP and kinds[k] not in ("table", "heading", "about"):
        if kinds[k] == "text":
            seen += 1
            if _is_footnote(lines[k].strip()):
                notes.append(lines[k].strip())
        k += 1
    return tuple(dict.fromkeys(notes))  # pages repeat footnotes verbatim; keep the first of each


def _about_end(lines: Sequence[str], kinds: Sequence[str], start: int) -> int:
    """Last index of the about tail: the marker's paragraph, plus the next paragraph when the marker line is
    only the caption (``**ABOUT DUPACO COMMUNITY CREDIT UNION:**``)."""
    end = start
    while end + 1 < len(lines) and kinds[end + 1] == "text":
        end += 1
    caption = re.sub(r"[*_:\s]+", " ", lines[start]).strip()
    caption_only = len(caption) <= 60 or caption == caption.upper()  # an inline body has lowercase text
    if end == start and caption_only:
        k = end + 1
        while k < len(lines) and kinds[k] in ("blank", "boiler"):
            k += 1
        if k < len(lines) and kinds[k] == "text":
            end = k
            while end + 1 < len(lines) and kinds[end + 1] == "text":
                end += 1
    return end


def _rate_word(sentence: str) -> bool:
    """Whether ``sentence`` has a rate word (``_RATE_WORD_RE``) other than a title-case ``Rate`` or ``Rates`` inside
    a capitalised name: one right after a capitalised word, so never sentence-initial (``... the FHLB Mortgage Rate
    Relief program``). ``Rates and introductory APR are accurate ...``, ``1Rates``, ``**Rates``, ``loan Rates`` and
    ``CST, Rates`` count: markup and footnote digits are no word, and punctuation after a word ends a name."""
    for m in _RATE_WORD_RE.finditer(sentence):
        if m.group(0) not in ("Rate", "Rates"):
            return True
        before = sentence[:m.start()]
        if not _NAME_WORD_RE.fullmatch(before.split()[-1] if before[-1:].isspace() and before.strip() else ""):
            return True
    return False


def _effective_cue(sentence: str) -> Optional[str]:
    """The valid date nearest after the word ``effective`` in one sentence, unless an end word (``through``,
    ``until``, ``expires``, ``valid``) comes first: ``Rates are effective as of 06/15/2026``, ``Effective February
    17, 2025``; never ``Rates effective immediately, offer valid through 12/31/2026``."""
    for m in EFFECTIVE_LINE_RE.finditer(sentence):
        after = sentence[m.end():]
        end = _END_WORD_RE.search(after)
        found = parse_date(after[:end.start()] if end else after)
        if found:
            return found
    return None


def _as_of_cue(sentence: str) -> Optional[str]:
    """The date right after ``as of`` in one sentence with a rate word (``_rate_word``): ``As of, 8/24/26, the
    tiered introductory rate structure is ...``; never ``As of 09/01/2026, we have 24 branches``."""
    for m in _AS_OF_DATE_RE.finditer(sentence):
        found = parse_date(m.group(1))
        if found:
            return found if _rate_word(sentence) else None
    return None


def _first_effective_date(lines: Sequence[str]) -> Optional[str]:
    """The first ``effective`` cue date in the sentences of ``lines``, else the first ``as of`` cue date: within
    one trailer or paragraph an effective line beats an as-of statement wherever it stands. A bare date (``Offer
    valid through 12/31/2026.``, a PDF footer, ``Updated 3/1/2026``) and a date before ``effective`` never count."""
    sentences = [sentence for line in lines for sentence in _SENTENCE_END_RE.split(line)]
    for cue in (_effective_cue, _as_of_cue):
        found = next((day for day in map(cue, sentences) if day), None)
        if found:
            return found
    return None


def _is_date_cue(line: str) -> bool:
    """A line that can date a table: one with the word ``effective`` (dated or not) or an ``as of`` cue date."""
    return bool(EFFECTIVE_LINE_RE.search(line)) or _first_effective_date([line]) is not None


def split_blocks(markdown: str, boilerplate: FrozenSet[str]) -> List[Block]:
    """Blocks in page order. A table block is the run of ``|`` lines plus its trailer (``_trailer``: the date-cue
    and footnote lines just below it). Table and prose blocks alike take ``effective_date`` only from an
    effective-date cue (``_first_effective_date``: ``effective`` before ``as of``), else ``None``. A table's
    ``effective`` lines are its alone; its footnote lines, its ``as of`` rate sentences and every other line below
    it also form prose blocks, paragraphs of text lines, so the inline pass reads every rate sentence after a
    table. When ``ABOUT_MARKER`` is in ``boilerplate``, a line starting with it opens an ``about_tail`` block.
    Headings and boilerplate lines belong to no block."""
    lines = [line.rstrip("\r") for line in (markdown or "").split("\n")]
    tail_on = ABOUT_MARKER in boilerplate
    kinds = [_line_kind(line, boilerplate, tail_on) for line in lines]
    paths = _heading_paths(lines, kinds)
    blocks: List[Block] = []
    consumed: Set[int] = set()  # the tables' effective lines that are not footnotes: never prose
    i = 0
    while i < len(lines):
        kind = kinds[i]
        if kind == "table":
            j = i
            while j < len(lines) and kinds[j] == "table":
                j += 1
            trailer, stop = _trailer(lines, kinds, j)
            tail = [lines[k].strip() for k in trailer]
            consumed.update(k for k, text in zip(trailer, tail)
                            if EFFECTIVE_LINE_RE.search(text) and not _is_footnote(text))
            body = [lines[k].strip() for k in range(i, j)] + tail
            end = trailer[-1] if trailer else j - 1
            blocks.append(Block("table", len(blocks), i + 1, end + 1, paths[i], tuple(body),
                                _first_effective_date(tail), _footnotes(lines, kinds, trailer, stop)))
            i = j
        elif kind == "about":
            end = _about_end(lines, kinds, i)
            body = tuple(lines[k].strip() for k in range(i, end + 1) if kinds[k] in ("about", "text"))
            blocks.append(Block("about_tail", len(blocks), i + 1, end + 1, paths[i], body, None, ()))
            i = end + 1
        elif kind == "text" and i not in consumed:
            j = i
            while j < len(lines) and kinds[j] == "text" and j not in consumed:
                j += 1
            body = tuple(lines[k].strip() for k in range(i, j))
            blocks.append(Block("prose", len(blocks), i + 1, j, paths[i], body, _first_effective_date(body), ()))
            i = j
        else:
            i += 1
    return blocks


def _clean_cell(cell: str) -> str:
    return cell.replace("\\*", "*").replace("\\|", "|").replace("\\r\\n", " ").strip()


def _split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [_clean_cell(c) for c in _PIPE_SPLIT_RE.split(s)]


def classify_cell(text: str) -> str:
    """Spike ``classify_cell``: ``empty``, ``model_year_tier``, ``balance_tier``, ``term`` or ``label``."""
    t = text.strip()
    if t in _EMPTY_CELLS:
        return "empty"
    if MODEL_YEAR_RE.search(t) and ("model year" in t.lower() or re.search(r"\d{4}\s*[–-]\s*\d{2}", t)):
        return "model_year_tier"
    if (re.search(r"\$[\d,]", t) and ("–" in t or "-" in t or "+" in t or "or less" in t.lower())
            and len(re.sub(r"[\d$,.\s–\-+]|or less", "", t, flags=re.I)) <= 2):
        return "balance_tier"
    if TERM_RE.search(t) and len(t) < 20:
        return "term"
    return "label"


def _is_text_label(cell: str) -> bool:
    """A ``label`` cell with three or more letters besides amounts and tier punctuation (``Roth: $15,000+``),
    unlike ``N/A`` or a bare amount."""
    leftover = re.sub(r"[\d$,.\s–\-+]|or less", "", cell, flags=re.I)
    return classify_cell(cell) == "label" and len(re.findall(r"[A-Za-z]", leftover)) >= 3


def _header_text(cell: str) -> str:
    t = re.sub(r"(?<=[A-Za-z.])\d{1,2}$", "", strip_footnote(cell))  # "Min. to Open2" -> "Min. to Open"
    return t.strip().strip("*").strip()


def _header_kind(cell: str) -> Optional[str]:
    t = _header_text(cell)
    if not t:
        return None
    for rx, kind in ATTR_BY_HEADER:
        if rx.search(t):
            return kind
    if BALANCE_HEADER_RE.match(t):
        return "balance_tier"
    return "label" if LABEL_HEADERS.search(t) else None


def infer_columns(header: Sequence[str], rows: Sequence[Sequence[str]]) -> List[Optional[str]]:
    """Column kind per header cell, from the header text and then the cell contents (spike lines 177-206):
    ``label``, ``term``, ``model_year``, ``balance_tier``, ``amount``, ``apy``, ``dividend_rate``, ``apr``,
    ``rate``, ``points``, ``payment_example``, ``min_to_open``, ``min_to_earn``, ``fee``, or ``None``.

    Departures from the spike: ``Balance Tier``/``Balance`` headers are ``balance_tier`` (the spike called
    them labels); the model-year override applies only to columns whose header is unknown, so a labelled
    first column such as ``Loan Program`` keeps its model-year cells as row labels; a label or unknown
    column whose cells are all money tiers becomes ``balance_tier``, and a ``balance_tier`` column holding
    any text label (``Roth: $15,000+`` under a ``Balance`` header, ``_is_text_label``) becomes ``label``;
    dash placeholders count as empty; and when no column is a label but some column is rate-like, an
    unknown first column of text cells becomes the label (card tables headed by the product name,
    ``| Platinum Credit Card | APR |``).
    """
    cols = [_header_kind(h) for h in header]
    for ci, kind in enumerate(cols):
        sample = [r[ci] for r in rows if ci < len(r) and r[ci].strip() not in _EMPTY_CELLS]
        if not sample:
            continue
        if kind == "balance_tier" and any(_is_text_label(c) for c in sample):
            kind = cols[ci] = "label"  # the IRA type ("Roth:", "Traditional:") is the row label
        if all(_APR_CELL_RE.search(c) for c in sample):
            cols[ci] = "apr"
        elif all(_APY_CELL_RE.search(c) for c in sample):
            cols[ci] = "apy"
        elif kind in (None, "label", "balance_tier") and all(TERM_RE.search(c) and len(c) < 20 for c in sample):
            cols[ci] = "term"
        elif kind is None and all(_MODEL_YEAR_CELL_RE.search(c) for c in sample):
            cols[ci] = "model_year"
        elif kind in (None, "label") and all(classify_cell(c) == "balance_tier" for c in sample):
            cols[ci] = "balance_tier"
        elif kind is None and all(PCT_RE.search(c) for c in sample):
            cols[ci] = "rate"
        elif kind is None and all(MONEY_RE.search(c) for c in sample):
            cols[ci] = "amount"
    if cols and cols[0] is None and "label" not in cols and any(c in RATE_LIKE for c in cols):
        first = [r[0] for r in rows if r and r[0].strip() not in _EMPTY_CELLS]
        if first and all(classify_cell(c) == "label" and re.search(r"[A-Za-z]{3}", c) for c in first):
            cols[0] = "label"
    return cols


def _parsed_table(block: Block) -> Optional[Tuple[List[str], List[str]]]:
    """``(header cells, table lines)`` of a table block with a usable header, else ``None``. Header-less:
    no delimiter row after the first row, a blank header, or a header cell holding a rate or an amount."""
    if block.kind != "table":
        return None
    table_lines: List[str] = []
    for line in block.lines:
        if not line.startswith("|"):
            break
        table_lines.append(line)
    if len(table_lines) < 2 or not SEP_RE.match(table_lines[1]):
        return None
    header = _split_row(table_lines[0])
    if not any(header) or any(_DATA_CELL_RE.search(h) for h in header):
        return None
    return header, table_lines


def table_header(block: Block) -> Tuple[str, ...]:
    """Header text per column, aligned with ``Row.columns``: cells unescaped, footnote markers and surrounding
    emphasis removed (the text ``infer_columns`` reads), so columns of the same kind stay distinguishable
    (``Dividend Rate for 1st 6 Months`` against ``Dividend Rate After Promotional Period``). ``()`` for a
    non-table block or a header-less table."""
    parsed = _parsed_table(block)
    return tuple(_header_text(cell) for cell in parsed[0]) if parsed else ()


def table_rows(block: Block) -> List[Row]:
    """Data rows of a table block. Header-less tables (see ``_parsed_table``) and tables with neither a
    label column nor a rate-like column yield no rows. ``cells`` align with ``columns``; ``label`` is the
    first label cell."""
    parsed = _parsed_table(block)
    if parsed is None:
        return []
    header, table_lines = parsed
    body = [(line, _split_row(line)) for line in table_lines[2:] if not SEP_RE.match(line)]
    body = [(line, cells) for line, cells in body if any(c for c in cells)]
    if not body:
        return []
    cols = tuple(infer_columns(header, [cells for _, cells in body]))
    if "label" not in cols and not any(c in RATE_LIKE for c in cols):
        return []
    label_at = cols.index("label") if "label" in cols else None
    width = len(cols)
    rows: List[Row] = []
    for row_idx, (line, cells) in enumerate(body):
        aligned = tuple((list(cells) + [""] * width)[:width])
        rows.append(Row(aligned[label_at] if label_at is not None else "", aligned, cols, row_idx, line))
    return rows
