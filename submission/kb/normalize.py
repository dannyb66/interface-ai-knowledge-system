"""Shared text, number, date and URL normalization; standard library only."""
from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import AbstractSet, FrozenSet, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit, urlunsplit

from . import lexicon as lx
from .branch_aliases import branch_aliases

# Verbatim from harness/scoring.py:31; tests/test_00_normalize.py pins the parity.
NUM_RE = re.compile(r"(\$)?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|percent)?", re.I)

PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MONEY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?")
TERM_RE = re.compile(r"(\d+)\s*[-\u2013\u2014 ]?\s*(months?|mos?|years?|yrs?)\b\.?", re.I)
MODEL_YEAR_RE = re.compile(
    r"(?:Model\s+Year\s+)?(\d{4})\s*[\u2013-]\s*(\d{2,4})\s*(?:Model\s+Year)?|(\d{4})\s+Model\s+Year(?:\s*\(and older\))?",
    re.I,
)

_DASH_RE = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")
_QUOTES = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
})
_AMPM_RE = re.compile(r"\b([ap])\.\s?m\.?")  # same rule as harness/scoring.py _norm
_SPACE_RE = re.compile(r"\s+")

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.I)
_BARE_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
_MONEY_VALUE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")
_TIER_SPAN_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*-\s*(\d[\d,]*(?:\.\d+)?)")  # "$10,000-24,999"
_OPEN_BELOW_RE = re.compile(r"\b(?:or less|and under|or under|up to|less than)\b", re.I)
_OPEN_ABOVE_RE = re.compile(r"\+|\b(?:or more|and (?:above|over|up)|or greater)\b", re.I)
_MY_RANGE_RE = re.compile(r"(?<!\d)(\d{4})\s*-\s*(\d{4}|\d{2})(?!\d)")
_MY_SINGLE_RE = re.compile(r"(?<!\d)(\d{4})\s+model\s+year", re.I)

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MONTH_NAME = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
               r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
# MM/DD/YYYY, M/D/YYYY, MM/DD/YY, or "Month D, YYYY" ("Sep 10, 2025 2:30:00 PM" and
# "Effective February 17, 2025" match on their date part).
_DATE_RE = re.compile(
    r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])"
    r"|\b" + _MONTH_NAME + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.I,
)
_ISO_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SLASH_DAY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_ISO_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_NAMED_MONTH_RE = re.compile(r"^" + _MONTH_NAME + r"\.?,?\s+(\d{4})$", re.I)


def normalize_dashes(text: Optional[str]) -> str:
    """Map hyphen, en/em dash, figure dash, horizontal bar and minus variants to ``-``."""
    return _DASH_RE.sub("-", text or "")


def scorer_norm(text: Optional[str]) -> str:
    """Verbatim copy of ``harness/scoring.py`` ``_norm`` (lines 49-52): the text the scorer's substring match sees."""
    s = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", (text or "").lower())   # "a.m." / "a.m" -> "am"
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def norm_text(text: Optional[str]) -> str:
    """Retrieval normaliser: lowercase, ``a.m.``/``p.m.`` collapsed as the scorer does, every hyphen, dash and
    minus variant mapped to ``-``, curly quotes straightened, spaces collapsed. It folds more than the scorer
    (U+2010-2012, U+2015, U+2212, curly quotes), so use ``scorer_norm`` to predict a scorer match."""
    s = _AMPM_RE.sub(r"\1m", (text or "").lower())
    s = normalize_dashes(s).translate(_QUOTES)
    return _SPACE_RE.sub(" ", s).strip()


def number_tokens(text: Optional[str]) -> Set[Tuple[str, float]]:
    """``(unit, value)`` pairs exactly as ``harness/scoring.py`` ``_numbers`` reads them."""
    out = set()
    for m in NUM_RE.finditer(text or ""):
        unit = "$" if m.group(1) else ("%" if m.group(4) else "")
        val = float(m.group(2).replace(",", "") + ("." + m.group(3) if m.group(3) else ""))
        out.add((unit, round(val, 4)))
    return out


def format_percent(value: float, decimals: int) -> str:
    """``4.1, 2`` -> ``"4.10%"``; rounds half up on the shortest repr, so 6.125 at 2 places is 6.13."""
    if decimals < 0:
        raise ValueError("decimals must be >= 0, got {}".format(decimals))
    quantum = Decimal(1).scaleb(-decimals)
    return "{:f}%".format(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def strip_footnote(cell: Optional[str]) -> str:
    """Drop footnote markers: a digit glued after ``%``, ``% APR``/``% APY`` or ``)``, ``[n](link)``, trailing ``*``,
    and a final digit set off by spaces after ``%`` or ``% APR``/``% APY`` (``15.50% 1``).

    Money and plain numbers are never touched (``$1,000.00`` stays ``$1,000.00``).
    """
    v = (cell or "").strip()
    v = re.sub(r"\[\d+\]\([^)]*\)", "", v)                       # "[2](...#fine-print)"
    v = re.sub(r"(?<=%)\d{1,2}(?![\d.,])", "", v)                  # "4.10%2" -> "4.10%"
    v = re.sub(r"(%\s*AP[RY])\d{1,2}\b", r"\1", v, flags=re.I)     # "5.39% APR1" -> "5.39% APR"
    v = re.sub(r"(?<=%)\s+\d{1,2}$", "", v)                        # "15.50% 1" -> "15.50%"
    v = re.sub(r"(%\s*AP[RY])\s+\d{1,2}$", r"\1", v, flags=re.I)   # "5.39% APR 1" -> "5.39% APR"
    v = re.sub(r"(?<=\))\d{1,2}\b", "", v)                         # "(APY)1" -> "(APY)"
    v = re.sub(r"(?<=\))\s+\d{1,2}$", "", v)                       # "(As Low As) 1" at the end
    v = re.sub(r"\\?\*+$", "", v)                                  # trailing "*" or "\*"
    return v.strip()


def parse_percent(text: Optional[str]) -> Optional[float]:
    """First ``N%`` (or ``N percent``) in ``text``; a cell holding only a number (points ``0``) parses as itself."""
    m = _PERCENT_RE.search(text or "")
    if m:
        return float(m.group(1))
    m = _BARE_NUMBER_RE.match(text or "")
    return float(m.group(1)) if m else None


def _money_values(text: str) -> List[float]:
    return [float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
            for m in _MONEY_VALUE_RE.finditer(text)]


def parse_money(text: Optional[str]) -> Optional[float]:
    """First dollar amount: ``$1,000.00``, ``$ 816.73`` and ``$832750`` all parse; no ``$`` gives ``None``."""
    values = _money_values(text or "")
    return values[0] if values else None


def parse_tier(text: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """``$10,000 – $24,999.99`` -> (10000.0, 24999.99); ``$25,000+`` -> (25000.0, None); ``$832750 or less`` -> (None, 832750.0)."""
    t = normalize_dashes(text)
    nums = _money_values(t)
    if nums and _OPEN_BELOW_RE.search(t):
        return (None, nums[0])
    if nums and _OPEN_ABOVE_RE.search(t):
        return (nums[0], None)
    if len(nums) >= 2:
        return (nums[0], nums[1])
    m = _TIER_SPAN_RE.search(t)
    if m:
        return (float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")))
    if nums:
        return (nums[0], nums[0])
    return (None, None)


def parse_term_months(text: Optional[str]) -> Optional[int]:
    """``30-Year`` -> 360, ``17 Month ...`` -> 17, ``(60 mo)`` -> 60; ``None`` when no term is present."""
    m = TERM_RE.search(text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * 12 if unit.startswith("y") else n


def _plausible_year(y: int) -> bool:
    return 1900 <= y <= 2100


def parse_model_years(text: Optional[str]) -> Optional[Tuple[int, int]]:
    """Sorted ``(min, max)``: ``2023–26 Model Year`` -> (2023, 2026), ``Model Year 2026-23`` -> (2023, 2026),
    ``2016 Model Year (and older)`` -> (0, 2016)."""
    t = normalize_dashes(text)
    m = _MY_RANGE_RE.search(t)
    if m:
        a, tail = int(m.group(1)), m.group(2)
        b = int(tail) if len(tail) == 4 else int(str(a)[:2] + tail)
        return (min(a, b), max(a, b)) if _plausible_year(a) and _plausible_year(b) else None
    m = _MY_SINGLE_RE.search(t)
    if m and _plausible_year(int(m.group(1))):
        y = int(m.group(1))
        return (0, y) if "older" in t.lower() else (y, y)
    return None


def _iso(y: int, mo: int, d: int) -> Optional[str]:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _month_number(name: str) -> int:
    return _MONTHS[name[:3].lower()]


def parse_date(text: Optional[str]) -> Optional[str]:
    """ISO date of the first valid date in ``text`` (MM/DD/YYYY, M/D/YYYY, MM/DD/YY, Month D, YYYY)."""
    for m in _DATE_RE.finditer(text or ""):
        if m.group(1):
            year = int(m.group(3))
            iso = _iso(year + 2000 if len(m.group(3)) == 2 else year, int(m.group(1)), int(m.group(2)))
        else:
            iso = _iso(int(m.group(6)), _month_number(m.group(4)), int(m.group(5)))
        if iso:
            return iso
    return None


def _last_day(y: int, mo: int) -> Optional[str]:
    if not 1 <= mo <= 12:
        return None
    return _iso(y, mo, calendar.monthrange(y, mo)[1])


def parse_as_of(text: Optional[str]) -> Optional[str]:
    """The whole string as a date: ISO, MM/DD/YYYY, YYYY-MM or Month YYYY (month forms give the last day)."""
    if not isinstance(text, str):
        return None
    s = text.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", s):
        s = s[:10]
    m = _ISO_DAY_RE.match(s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _SLASH_DAY_RE.match(s)
    if m:
        return _iso(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = _ISO_MONTH_RE.match(s)
    if m:
        return _last_day(int(m.group(1)), int(m.group(2)))
    m = _NAMED_MONTH_RE.match(s)
    if m:
        return _last_day(int(m.group(2)), _month_number(m.group(1)))
    return None


def _word_before(s: str, start: int) -> str:
    return s[max(0, s.rfind(" ", 0, max(0, start - 1)) + 1):start].strip(" " + lx.NAME_PUNCT)


def _day(text: object) -> Optional[date]:
    """``YYYY-MM-DD`` as a date (a longer ISO string is cut to its first 10 characters); anything else is ``None``."""
    if not isinstance(text, str):
        return None
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def question_dates(s: str, reference: Optional[str] = None) -> List[str]:
    """ISO dates written in a question (``norm_text`` output, patterns from ``lexicon.py``), in text order; a month
    without a year takes the next written year (``between May and September 2026``), else the one before, else the
    ``reference`` day's year, a later month too (the near future; a bare "may" after "and"/"or" with a word after it is
    the verb), and a bare month counts only after a date word (``in May``), as does a ``YYYY-MM`` (``as of
    2026-05``); a month is its last day unless a day or qualifier says else."""
    ref = _day(reference)
    found = []  # (start, year, month, day); day None is the month's last day
    for m in lx.NUM_DATE_RE.finditer(s):
        y, mo, d = (m.group(3), m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        found.append((m.start(), int(y), int(mo), int(d)))
    for m in lx.YEAR_MONTH_RE.finditer(s):
        if _word_before(s, m.start()) in lx.DATE_LEAD:
            found.append((m.start(), int(m.group(1)), int(m.group(2)), None))
    mentions = []
    for m in lx.MONTH_RE.finditer(s):
        qual, month, day, year = m.groups()
        before, after = _word_before(s, m.start()), s[m.end():m.end() + 2]
        if before == "the":
            before = _word_before(s, max(0, m.start() - 4))
        if qual or day or year or before in lx.DATE_LEAD:  # "fixed and may change": "may" is the verb
            verb = month == "may" and not (qual or day or year) and before in lx.MODAL_LEADS and after[1:].isalpha()
            mentions.append((m.start(), qual, lx.MONTHS[month], day, year, verb))
    years = [mention[4] for mention in mentions]
    for k, (start, qual, month, day, year, verb) in enumerate(mentions):
        later, earlier = [y for y in years[k + 1:] if y], [y for y in years[:k] if y]
        year = year or (later[0] if later else earlier[-1] if earlier else None)
        if year is None and ref is not None and not verb:
            year = ref.year  # "still open in October?" with a September reference: this October (ruling 6)
        if year is not None:
            found.append((start, int(year), month, int(day) if day else lx.QUAL_DAY.get(qual or "")))
    out: List[str] = []
    for _, y, mo, d in sorted(found, key=lambda f: f[0]):  # text order; starts are distinct
        try:
            if 1900 <= y <= 2100:
                out.append(date(y, mo, calendar.monthrange(y, mo)[1] if d is None else d).isoformat())
        except ValueError:  # 02/30/2026, month 13: not a date
            continue
    return out


_ONES = dict(zip("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(1, 20)))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
_WORD_TERM = re.compile(r"\b((?:" + "|".join(_TENS) + r")(?:[- ](?:" + "|".join(list(_ONES)[:9]) + r"))?|" + "|".join(_ONES) + r")[ -](months?|mos?|years?|yrs?)\b")


def number_word(text: str) -> Optional[int]:
    words = text.lower().replace("-", " ").split()
    if len(words) == 1:
        return _ONES.get(words[0], _TENS.get(words[0]))
    if len(words) == 2 and words[0] in _TENS and words[1] in _ONES and _ONES[words[1]] < 10:
        return _TENS[words[0]] + _ONES[words[1]]
    return None


def question_term(s: str) -> Optional[Tuple[int, bool, bool]]:
    """The first term written in a question as (months, written in years, a rate word right after it): ``17-month``
    is (17, False, False), ``30-year`` (360, True, False), ``the 15-year rate`` (180, True, True)."""
    s = _WORD_TERM.sub(lambda m: str(number_word(m[1])) + "-" + m[2], s)
    m = lx.TERM_RE.search(s)
    if m is None:
        return None
    years = m.group(2)[0] == "y"
    return int(m.group(1)) * (12 if years else 1), years, lx.TERM_RATE_RE.match(s, m.end()) is not None


def question_amount(s: str) -> Optional[float]:
    """The first dollar amount written in a question: ``$25,000``, ``$1.5 million``, ``$50k``. An upper bound ("under
    $100,000", "$100,000 or less": ``lexicon.UPPER_BOUND_BEFORE_RE``, ``UPPER_BOUND_AFTER_RE``) is read a cent below
    it, so it reaches no inclusive minimum (a jumbo row's $100,000 to earn) and stays in a tier that ends at it."""
    m = lx.AMOUNT_RE.search(s)
    if m is None:
        return None
    scale = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6}.get(m.group(3) or "", 1.0)
    value = float(m.group(1).replace(",", "") + (m.group(2) or "")) * scale
    below = (lx.UPPER_BOUND_BEFORE_RE.search(s, max(0, m.start() - 24), m.start())
             or lx.UPPER_BOUND_AFTER_RE.match(s, m.end()))
    return value - 0.01 if below else value


def model_year_range(toks: Sequence[str], i: int) -> Optional[Tuple[int, int]]:
    """Both ends, in order, of a model-year range written around the year at ``toks[i]``: a year right before or after
    it (``the 2024-2027 model years``, ``model year 2024-2027``; the word tokens drop the dash) or one
    ``YEAR_RANGE_WORDS`` word away (``a 2021 to 2023 model``, ``between 2021 and 2023 model years``), each 1980-2099;
    ``None`` for a single year (fix round 4, N2; "and": fix round 5, D)."""
    def year(j: int) -> Optional[int]:
        t = toks[j] if 0 <= j < len(toks) else ""
        return int(t) if len(t) == 4 and t.isdigit() and 1980 <= int(t) <= 2099 else None
    here = year(i)
    for j, between in ((i - 1, ()), (i + 1, ()), (i - 2, (i - 1,)), (i + 2, (i + 1,))):
        there = year(j)
        if here is not None and there is not None and there != here and all(
                toks[k] in lx.YEAR_RANGE_WORDS for k in between):
            return min(here, there), max(here, there)
    return None


def year_back(toks: Sequence[str]) -> bool:
    """A ``PAST_WORDS`` word right before "year" that no ``VEHICLE_WORDS`` word follows: "in the previous year", "the
    prior year" ask a date one year back (the canonicaliser's ``year_back`` slot; fix round 4, N4), while "a prior-year
    model car" names a model year; the possessive "year's" (``years``) is not read."""
    return any(t in lx.PAST_WORDS and tuple(toks[i + 1:i + 2]) == ("year",)
               and not set(toks[i + 2:i + 3]) & lx.VEHICLE_WORDS for i, t in enumerate(toks))


def polite_request(toks: Sequence[str]) -> bool:
    """A request phrased as a question (word tokens): "Can you tell me ...", "Do you know the ...", "May I see ..."."""
    head = list(toks[:5])
    if head[:2] in (["can", "you"], ["could", "you"], ["would", "you"], ["will", "you"]):
        rest = head[3:] if head[2:3] == ["please"] else head[2:]
        return bool(rest) and rest[0] in lx.REQUEST_VERBS and not set(rest[1:3]) & {"if", "whether"}
    if head[:3] == ["do", "you", "know"]:
        return not set(head[3:4]) & {"if", "whether"}
    if head[:2] in (["can", "i"], ["could", "i"], ["may", "i"]):
        return head[2:3] in (["see"], ["know"], ["ask"]) or (
            head[2:3] in (["get"], ["have"]) and head[3:4] in (["the"], ["your"], ["all"]))
    return False


def passive_used_to(toks: Sequence[str], i: int) -> bool:
    """Whether "used to" at ``i`` is the passive ("is the HSA used to pay for", "can be used to pay", "get used to"): a
    ``USED_TO_PASSIVE`` word right before it, or a ``BE_FORMS`` word earlier with no ``USED_TO_CLAUSE`` word between;
    "used to be" is always the past habit."""
    if tuple(toks[i:i + 2]) != ("used", "to") or tuple(toks[i + 2:i + 3]) == ("be",):
        return False
    if i > 0 and toks[i - 1] in lx.USED_TO_PASSIVE:
        return True
    for j in range(i - 1, -1, -1):  # "What was the rate that the special used to pay?": the clause word ends the search
        if toks[j] in lx.USED_TO_CLAUSE:
            return False
        if toks[j] in lx.BE_FORMS:
            return True
    return False


def past_wording(toks: Sequence[str], rate_at: AbstractSet[int]) -> Tuple[bool, FrozenSet[int]]:
    """Explicit past-value wording in word tokens (the rules at ``lexicon.PAST_WORDS``; ``rate_at`` holds the starts of
    rate words): (found, the indices of the change words in "before it changed" and its kin, no change cue then)."""
    found, quiet = False, set()
    def subject(j: int) -> str:  # the word before toks[j], a relative "that"/"which"/"who" skipped
        k = j - 2 if j > 1 and toks[j - 1] in lx.RELATIVE_WORDS else j - 1
        return toks[k] if k >= 0 else ""
    asks = [(j, w) for j, w in enumerate(toks) if (w in lx.PAST_ASKED or w in lx.PERFECT_HEADS)
            and subject(j) not in lx.HISTORY_SUBJECTS]  # "the APY that was ...", not "if the car was ..." (F6 leftover)
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        told = (nxt.endswith("ed") and nxt not in lx.RATE_PARTICIPLES) or nxt in lx.HISTORY_VERBS or nxt == "been"
        history = t in lx.PAST_ADVERBS and told and not any(
            j < i and (w in lx.PAST_ASKED or nxt == "been") for j, w in asks)  # "a car previously financed elsewhere"
        if (t in lx.PAST_WORDS and nxt not in lx.NOT_PAST_NEXT and (t, nxt) != ("prior", "to") and not history) or (
                t == "old" and i + 1 in rate_at) or (t == "used" and nxt == "to" and not passive_used_to(toks, i)):
            found = True
        if t != "before" and (t, nxt) != ("prior", "to"):
            continue
        start = j = i + 1 if t == "before" else i + 2
        while j < len(toks) and j < start + 4 and toks[j] in lx.PAST_FILLER:
            j += 1
        fill, word = toks[start:j], toks[j] if j < len(toks) else ""
        updown = word in ("went", "gone") and toks[j + 1:j + 2] in (["up"], ["down"])
        verb = word in lx.PAST_CHANGED and fill and (updown or word not in ("went", "gone"))
        noun = word in lx.PAST_CHANGE and fill and fill[-1] in (lx.PAST_DETERMINERS if word.endswith("s") else
                                                                lx.PAST_NOUN_LEAD)
        if verb or noun:
            found = True
            quiet.update(range(j, j + 2 if updown else j + 1))
    return found, frozenset(quiet)


def branch_name(s: str) -> Optional[str]:
    """Up to three words before ``branch``/``office``/``location`` in a question (``the Mullan Avenue branch``), else
    the word after ``branch in``/``branch at``."""
    s = re.sub(r",\s*(?:il|ia|wi)\b", "", branch_aliases(s))
    words = s.split(" ")
    for i, raw in enumerate(words):
        if raw.strip(lx.NAME_PUNCT).split("'")[0] not in ("branch", "branches", "office", "location"):  # "branch's"
            continue
        name: List[str] = []
        for prev in reversed(words[max(0, i - 3):i]):
            word = prev.strip(lx.NAME_PUNCT)
            word = word[:-2] if word.endswith("'s") else word
            if not word or word in lx.NAME_STOP:
                break
            name.insert(0, word)
        if name:
            return " ".join(name)
        after = ""
        if words[i + 1:i + 2] in (["in"], ["at"]) and i + 2 < len(words):
            after = words[i + 2].strip(lx.NAME_PUNCT)
        if after and after not in lx.NAME_STOP and not after.isdigit() and after not in lx.DAY_WORDS:
            return after
    return None


_BARE_NAMES = tuple(sorted(lx.BRANCH_NAMES, key=lambda name: (-len(name), name)))  # the longest first
_JOINER_RE = re.compile(r"[a-z0-9&]+")  # the words between two branch names


def _bare_spans(s: str) -> List[Tuple[int, int, str]]:
    """``(start, end, name)`` of each ``lexicon.BRANCH_NAMES`` name the ``norm_text`` question writes as whole words, in
    the order written; the longest name wins where two overlap (``mineral point`` in ``mineral point road``)."""
    s = branch_aliases(s)
    spans: List[Tuple[int, int, str]] = []
    for name in _BARE_NAMES:
        at = s.find(name)
        while at >= 0:
            end = at + len(name)
            if not (s[at - 1:at].isalnum() or s[end:end + 1].isalnum() or any(a < end and at < b for a, b, _ in spans)):
                spans.append((at, end, name))
            at = s.find(name, at + 1)
    return sorted(spans)


def bare_names(s: str) -> List[str]:
    """The distinct branch names a question writes with no branch word needed (``What are the lobby hours in Waukee?``,
    ``Hy-Vee's``), in the order written (``_bare_spans``)."""
    return list(dict.fromkeys(name for _, _, name in _bare_spans(s)))


def bare_branch(s: str) -> Optional[str]:
    """The branch a question names with no branch word: its one bare name, or with two or more the first written when
    no ``lexicon.NAME_JOINERS`` word comes between two of them (``the Hy-Vee in Dubuque``, ``Hillcrest Rd., Dubuque``:
    a branch and its city; a comma alone joins none); ``None`` when none is written or a joiner lists several ("the
    Cedar Rapids and Waukee lobby hours": Task 12 review M2, until a multi-branch slot exists)."""
    s = branch_aliases(s)
    spans = _bare_spans(s)
    names = list(dict.fromkeys(name for _, _, name in spans))
    if len(names) > 1 and any(set(_JOINER_RE.findall(s[end:start])) & lx.NAME_JOINERS
                              for (_, end, _), (start, _, _) in zip(spans, spans[1:])):
        return None
    return names[0] if names else None


def _clean_query(query: str) -> str:
    pieces = [p for p in query.split("&") if p]
    keys = [p.split("=", 1)[0].lower() for p in pieces]
    if "campaignid" in keys:  # HubSpot modal URLs: the whole query is tracking
        return ""
    return "&".join(p for p, k in zip(pieces, keys) if k != "hslang")


def canonical_url(url: Optional[str]) -> str:
    """Lowercase scheme and host; drop ``hsLang``, HubSpot ``campaignId`` queries, the fragment and a trailing slash."""
    raw = (url or "").strip()
    if "//" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), _clean_query(parts.query), ""))
