"""Shared pieces of scripts/build_proxy_set.py: the split rule, grader tokens, value-in-force pools, the dated
selection, tier amounts, the ambiguity guard and question rendering. Standard library plus the kit's scorer and
``kb.normalize``; deterministic (no set or dict order reaches a result)."""
from __future__ import annotations

import hashlib
import re
import string
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

from kb.normalize import norm_text  # noqa: E402
from kb.temporal import select_dated  # noqa: E402
from scoring import NUM_RE, contains, _numbers as grader_numbers  # noqa: E402,F401

PROXY_DIGITS = "0123456789abc"  # a sha1 whose last hex digit is one of these: the proxy's key
JACCARD_MAX = 0.8
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PROGRAMS = {"roth": "Roth", "traditional": "traditional"}  # IRA programs; a mortgage's program is its product name
UNITS = {"pct": "%", "usd": "$"}
FLAGS = ("jumbo", "special", "intro")  # boolean qualifiers: a missing one reads as False
# placeholder -> the qualifier it states (an asked amount states a balance or a loan-amount tier)
STATES = {"term": "term_months", "months": "term_months", "years": "term_months", "jumbo": "jumbo",
          "special": "special", "intro": "intro", "program": "program", "model_year": "model_year",
          "loan_amount": "amount", "amount": "amount"}
# placeholder -> the qualifier it renders: a key holding that qualifier needs it non-empty
NEEDS = {"term": "term_months", "months": "term_months", "years": "term_months", "program": "program",
         "model_year": "model_year_max", "day": "day", "year": "year", "branch": "branch_name"}
PLACEHOLDERS = frozenset(STATES) | {"name", "attr", "date", "date_from", "date_to", "branch", "day", "year"}
_FORMATTER = string.Formatter()


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def in_split(key: Any, split: str) -> bool:
    """The split rule: the proxy takes a key whose ``sha1(repr(key))`` ends in a hex digit below ``d``."""
    return (sha(repr(key))[-1] in PROXY_DIGITS) == (split == "proxy")


def words(question: str) -> List[str]:
    """Word tokens as tests/test_60_proxy.py reads them: lowercased, all but a-z, 0-9 and spaces dropped."""
    return re.sub(r"[^a-z0-9 ]", "", question.lower()).split()


def known_questions(questions: Sequence[str]) -> List[Tuple[str, List[str], set]]:
    return [(norm_text(q), words(q), set(words(q))) for q in questions]


def near_duplicate(question: str, known: Sequence[Tuple[str, List[str], set]]) -> bool:
    """Equal ``norm_text`` or word tokens, or a token Jaccard above ``JACCARD_MAX``, with any known question."""
    norm, toks = norm_text(question), words(question)
    bag = set(toks)
    return any(norm == k_norm or toks == k_toks or len(bag & k_bag) / max(1, len(bag | k_bag)) > JACCARD_MAX
               for k_norm, k_toks, k_bag in known)


def shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def day_phrase(day: str) -> str:
    """``2026-05-18`` -> ``May 18, 2026`` (fixed English month names: no locale)."""
    year, month, dom = (int(part) for part in day.split("-"))
    return "%s %d, %d" % (MONTH_NAMES[month - 1], dom, year)


def money(amount: float) -> str:
    return "${:,}".format(int(amount)) if amount == int(amount) else "${:,.2f}".format(amount)


def value_token(f: Any) -> Optional[str]:
    """The value as a grader token: the number as printed with its unit ("4.10%", "$1,000.00", "22"); a text fact's
    ``value_text`` when it holds a digit (hours, dates); None for "Closed", "ATM only", "N/A" and other digit-free
    values, which an all-branches list would hold too."""
    if f.unit == "text":
        return f.value_text if re.search(r"\d", f.value_text) else None
    if f.value is None:
        return None
    unit = UNITS.get(f.unit, "")
    for m in NUM_RE.finditer(f.value_text):
        printed = m.group(2) + ("." + m.group(3) if m.group(3) else "")
        if round(float(printed.replace(",", "")), 4) == round(float(f.value), 4):
            return "$" + printed if unit == "$" else printed + unit
    printed = ("%.4f" % f.value).rstrip("0").rstrip(".")
    return "$" + printed if unit == "$" else printed + unit


def trap_token(f: Any) -> Optional[str]:
    """A wrong value as a must_not_include token: a count keeps the word after it ("24 branch": a bare 24 would hit
    "24-hour"); any other value is its ``value_token``."""
    token = value_token(f)
    if token is None or f.unit != "count":
        return token
    m = re.search(re.escape(token) + r"\s+([A-Za-z]+)", f.value_text)
    return token + " " + m.group(1) if m else token


def same_value(f: Any, g: Any) -> bool:
    """Equal as the grader reads them: numbers by value and unit, text values by their text."""
    if f.unit == "text" or g.unit == "text":
        return f.unit == g.unit and f.value_text == g.value_text
    if f.value is None or g.value is None:
        return f.value is None and g.value is None
    return f.unit == g.unit and round(float(f.value), 4) == round(float(g.value), 4)


def pool(store: Any, sid: str, pid: str, attr: str, day: Optional[str]) -> Dict[Any, Any]:
    """The facts a (pid, attr) question asked for ``day`` is answered from in crawl ``sid``, one per key in rank order:
    in force that day (``FactStore.in_force``), the top authority class only, table rows only when there are any."""
    try:
        facts = store.in_force(sid, pid, attr, day)
    except KeyError:
        return {}
    top = max((f.source.authority for f in facts), default=None)
    facts = [f for f in facts if f.source.authority == top]
    if any(f.qualifiers for f in facts):
        facts = [f for f in facts if f.qualifiers]
    out: Dict[Any, Any] = {}
    for f in facts:
        out.setdefault(f.key, f)
    return out


def loan_lows(facts: Dict[Any, Any]) -> Dict[Any, float]:
    """Each loan-amount tier's exclusive lower end: the next smaller ``loan_amount_max`` among keys alike otherwise."""
    rows: Dict[Tuple, List[Tuple[float, Any]]] = {}
    for key in facts:
        q = dict(key[2])
        if "loan_amount_max" in q:
            rows.setdefault(tuple(p for p in key[2] if p[0] != "loan_amount_max"), []).append((q["loan_amount_max"], key))
    lows: Dict[Any, float] = {}
    for tiers in rows.values():
        low = 0.0
        for top, key in sorted(tiers, key=lambda t: (t[0], repr(t[1]))):
            lows[key], low = low, top
    return lows


def tier_amount(q: Dict[str, Any], low: float) -> Optional[float]:
    """A round amount inside the key's balance or loan-amount tier: two significant digits of its middle (the open
    top tier: twice its floor); None for a key without such a tier."""
    if "balance_min" in q or "balance_max" in q:
        lo, hi, open_low = q.get("balance_min", 0.0), q.get("balance_max"), False
    elif "loan_amount_max" in q:
        lo, hi, open_low = low, q["loan_amount_max"], True
    else:
        return None
    if hi is None:
        return max(100.0, lo * 2)
    if hi < 100:
        return None
    mid = (max(lo, 100.0) + hi) / 2.0
    step = 10 ** max(0, len(str(int(mid))) - 2)
    for amount in (float(int(mid // step) * step), float(int(mid))):
        if (lo < amount if open_low else lo <= amount) and amount <= hi:
            return amount
    return None


def fits(q2: Dict[str, Any], q: Dict[str, Any], stated: set, year: Optional[int], amount: Optional[float],
         low: float) -> bool:
    """Whether a key with qualifiers ``q2`` fits a question that states ``stated`` of key ``q`` (unstated ones fit)."""
    for name in ("term_months", "program"):
        if name in stated and q2.get(name) != q.get(name):
            return False
    for flag in FLAGS:
        if flag in stated and bool(q2.get(flag)) != bool(q.get(flag)):
            return False
    if year is not None and ("model_year_min" in q2 or "model_year_max" in q2):
        if not q2.get("model_year_min", 0) <= year <= q2.get("model_year_max", float("inf")):
            return False
    if amount is not None:
        if ("balance_min" in q2 or "balance_max" in q2) and not (
                q2.get("balance_min", 0.0) <= amount <= q2.get("balance_max", float("inf"))):
            return False
        if "loan_amount_max" in q2 and not low < amount <= q2["loan_amount_max"]:
            return False
    return True


def ambiguous(facts: Dict[Any, Any], key: Any, f: Any, stated: set, year: Optional[int],
              amount: Optional[float]) -> bool:
    """Another key of the pool fits the question and holds another value."""
    q, lows = dict(key[2]), loan_lows(facts)
    return any(k2 != key and not same_value(g, f) and fits(dict(k2[2]), q, stated, year, amount, lows.get(k2, 0.0))
               for k2, g in facts.items())


def branch_display(name: str) -> str:
    """``east washington, madison`` -> ``East Washington``: the branch as a member names it."""
    return name.split(",")[0].strip().title()


def asked_day(label: Optional[str]) -> str:
    """A day inside a printed day range, the middle one (``monday-thursday`` -> ``Wednesday``); "" for no range."""
    ends = (label or "").split("-")
    if not label or ends[0] not in WEEK or ends[-1] not in WEEK:
        return ""
    a, b = WEEK.index(ends[0]), WEEK.index(ends[-1])
    span = [WEEK[(a + k) % 7] for k in range((b - a) % 7 + 1)]
    return span[len(span) // 2].title()


def fields(pattern: str) -> List[str]:
    return [name for _, name, _, _ in _FORMATTER.parse(pattern) if name]


def tidy(text: str) -> str:
    """Spaces collapsed, none before punctuation, and "a" before a vowel or an 8, 11 or 18 term made "an"."""
    text = re.sub(r" ([?.,!;:])", r"\1", re.sub(r"\s+", " ", text).strip())
    return re.sub(r"\b([Aa]) (?=[AEIOaeio]|(?:8\d*|11|18)-)", r"\1n ", text)


class Ctx:
    """The ingested store, its crawls and their day windows, the split and the template file's wording; pools cached."""

    def __init__(self, store: Any, split: str, templates: Dict[str, Any]) -> None:
        self.store, self.split = store, split
        crawls = store.snapshots()
        self.ids = [sid for sid, _ in crawls]
        self.days = [day for _, day in crawls]
        self.latest = len(self.ids) - 1
        # a crawl's window ends the day before the next crawl; the newest crawl's is its own day
        self.ends = [shift(self.days[i + 1], -1) for i in range(self.latest)] + [self.days[-1]]
        self.names = templates.get("names", {})
        self.name_sets = templates.get("name_sets", {})
        self.attributes = templates.get("attributes", {})
        self._pools: Dict[Tuple, Dict[Any, Any]] = {}

    def pool(self, i: int, pid: str, attr: str, day: Optional[str]) -> Dict[Any, Any]:
        k = (i, pid, attr, day)
        if k not in self._pools:
            self._pools[k] = pool(self.store, self.ids[i], pid, attr, day)
        return self._pools[k]

    def contested(self, i: int, key: Any, f: Any, day: str) -> bool:
        """A day after crawl ``i``'s own on which a later crawl's notice already dates another value: that crawl's
        pooled fact for ``key`` holds a value other than ``f``'s with an effective date ``e``, taken_i < e <= day. The
        crawl-window convention (``FactStore.snapshot_for``) and that notice disagree there (review C1)."""
        if day <= self.days[i]:
            return False
        for j in range(i + 1, self.latest + 1):
            g = self.pool(j, key[0], key[1], None).get(key)
            if g is not None and not same_value(g, f) and g.effective_date and self.days[i] < g.effective_date <= day:
                return True
        return False

    def candidate_days(self, i: int, key: Any, f: Any, last_day: bool = True) -> List[str]:
        """Crawl ``i``'s first, middle and last day, from the one the key's hash picks onwards, the days ``contested``
        for ``f``'s value left out (the crawl's own day never is); without ``last_day`` the last day only comes last,
        as a fallback (a change asked "between September 27 and September 28" reads oddly)."""
        first, last = self.days[i], self.ends[i]
        middle = shift(first, (date.fromisoformat(last) - date.fromisoformat(first)).days // 2)
        days = [first, middle, last] if last_day else [first, middle]
        k = int(sha(repr(key) + "|" + self.ids[i]), 16) % len(days)
        return [d for d in dict.fromkeys(days[k:] + days[:k] + [last]) if not self.contested(i, key, f, d)]

    def asked_day(self, i: int, key: Any, f: Any, last_day: bool = True) -> Optional[Tuple[str, Dict[Any, Any], Any]]:
        """(day, pool, fact): the first of crawl ``i``'s candidate days on which ``key`` is in force with ``f``'s
        value, or None."""
        for day in self.candidate_days(i, key, f, last_day):
            facts = self.pool(i, key[0], key[1], day)
            g = facts.get(key)
            if g is not None and same_value(g, f):
                return day, facts, g
        return None

    def dated(self, pid: str, attr: str) -> List[Any]:
        """The newest crawl's dated facts of the pair, newest publication per key."""
        facts = self.store.by_product_attr[self.ids[self.latest]].get((pid, attr), [])
        return select_dated([f for f in facts if f.published_date], None)


def render(ctx: Ctx, spec: Dict[str, Any], tpl: Dict[str, Any], key: Any, extra: Dict[str, str],
           amount: Optional[float] = None) -> Optional[Tuple[str, set, Optional[int], Optional[float]]]:
    """(question, the qualifiers it states, its model year, its amount) for ``key``, or None when the wording cannot
    say what the key needs (no name for the product, or a qualifier placeholder left empty)."""
    pid, attr, q = key[0], key[1], dict(key[2])
    text = tpl["text"]
    asks_amount = "amount" in fields(text)
    term, year, loan = q.get("term_months"), q.get("model_year_max") or q.get("model_year_min"), q.get("loan_amount_max")
    values = {"term": "%d-month" % term if term else "", "months": "%d" % term if term else "",
              "years": "%d-year" % (term // 12) if term and term % 12 == 0 else "",
              "jumbo": "jumbo" if q.get("jumbo") else "", "special": "special" if q.get("special") else "",
              "intro": "intro" if q.get("intro") else "", "program": PROGRAMS.get(q.get("program"), ""),
              "model_year": "%d" % year if year else "",
              "loan_amount": "" if asks_amount or not loan else " for loans of %s or less" % money(loan)}
    values.update(extra)
    name = attr_phrase = None
    if "name" in fields(text):
        names = dict(ctx.names)
        names.update(spec.get("names", {}))
        names.update(ctx.name_sets.get(tpl.get("name_set", ""), {}))
        name = names.get(pid)
        if name is None:
            return None
    if "attr" in fields(text):
        attrs = dict(ctx.attributes)
        attrs.update(tpl.get("attr_words", {}))
        attr_phrase = attrs.get(attr, attr.replace("_", " "))
    used = {n for piece in (text, name or "", attr_phrase or "") for n in fields(piece)}
    if any(NEEDS[n] in q and not values.get(n) for n in used if n in NEEDS):
        return None
    if name is not None:
        values["name"] = tidy(name.format(**values))
    if attr_phrase is not None:
        values["attr"] = tidy(attr_phrase.format(**values))
    stated = {STATES[n] for n in used if n in STATES}
    asked = amount if asks_amount else (loan - 0.01 if values["loan_amount"] else None)
    return tidy(text.format(**values)), stated, (year if "model_year" in stated else None), asked
