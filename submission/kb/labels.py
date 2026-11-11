"""Rows in words (spec section 7.4): each product's display name and a fact's label, out of ``compose.py``.

``label`` names one table row: program, term, certificate flags and branch before the product name, then the tier
ranges in words. Its numbers are the resolver's tier bounds plus any digit in a product name (``1st Rate
Checking``). ``phrase`` states the row's values: the asked column with its unit word, then each companion column
(a rate's APR) in parentheses. ``title_words`` capitalises a normalised qualifier and ``sentence`` ends a line with
a full stop. ``compose`` re-exports ``label`` and ``product_names``. Stdlib only; the one read is the registry's
display names, cached on first use.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import List, Mapping, Optional, Tuple

from .config import DEFAULT_DATA_DIR
from .types import Fact

Row = Tuple[Fact, ...]  # one table row: the asked column, then its companion columns (a rate's APR)
_UNIT_WORDS = {"apy": "APY", "apr": "APR", "rate": "rate", "dividend_rate": "dividend rate", "points": "points",
               "min_to_open": "minimum to open", "min_to_earn": "minimum balance to earn the APY",
               "payment_example": "example monthly payment", "fee": "fee"}
_PROGRAM_WORDS = {"roth": "Roth", "traditional": "Traditional"}  # mortgage programs are in the product names
_MORTGAGE_PROGRAMS = frozenset({"purchase", "refi"})  # their terms read in years: "30-Year Fixed"
_WORD_START_RE = re.compile(r"(^|[\s-])([a-z])")


@lru_cache(maxsize=None)
def product_names(path: Optional[Path] = None) -> Mapping[str, str]:
    """Each product id's first registry name, read once from ``data/products.json`` (``path`` overrides)."""
    target = Path(path) if path is not None else DEFAULT_DATA_DIR / "products.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    return MappingProxyType({p["product_id"]: p["names"][0] for p in data["products"]})


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _whole(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _money(value: float) -> str:
    """``$25,000`` for a whole amount, ``$24,999.99`` otherwise: the numbers of the resolver's tier bounds."""
    return "${:,.0f}".format(value) if float(value).is_integer() else "${:,.2f}".format(value)


def title_words(text: object) -> str:
    """Each word of a normalised qualifier capitalised: ``oldenburg ln., galena`` -> ``Oldenburg Ln., Galena``."""
    return _WORD_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), str(text))


def sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def _tiers(q: Mapping[str, object]) -> List[str]:
    """The tier ranges in words: balance, loan amount, model years, then the rate period and the day."""
    out = []
    low, high = q.get("balance_min"), q.get("balance_max")
    if _is_number(low) and _is_number(high):
        out.append("{} to {}".format(_money(low), _money(high)))
    elif _is_number(low):
        out.append("{} or more".format(_money(low)))
    elif _is_number(high):
        out.append("{} or less".format(_money(high)))
    if _is_number(q.get("loan_amount_max")):
        out.append("{} or less".format(_money(q["loan_amount_max"])))
    low, high = q.get("model_year_min"), q.get("model_year_max")
    if _is_number(high):
        if not _is_number(low) or low == 0:  # "2016 Model Year (and older)" starts at 0
            out.append("{} and older model years".format(_whole(high)))
        else:
            out.append("{}-{} model years".format(_whole(low), _whole(high)) if low != high
                       else "{} model year".format(_whole(high)))
    if q.get("intro"):
        out.append("introductory rate")
    if q.get("day"):
        out.append(title_words(q["day"]))
    if q.get("year"):
        out.append(str(q["year"]))
    return out


def label(fact: Fact, registry_names: Mapping[str, str]) -> str:
    """The row in words: program, term, certificate flags and branch before the product name, then the tiers.

    ``17 Month Fixed Jumbo Certificate Special``, ``30-Year Fixed Home Loans - Purchase, $100,000 or less``,
    ``Share Savings, $25,000 or more``, ``48 Month Auto Loan, 2016 and older model years``. Its numbers are the
    resolver's tier bounds, plus any digit in a product name (``1st Rate Checking``).
    """
    q = dict(fact.qualifiers)
    name = registry_names.get(fact.product_id) or title_words(fact.product_id.replace("_", " "))
    program = q.get("program")
    head = [_PROGRAM_WORDS[program]] if program in _PROGRAM_WORDS else []
    term = q.get("term_months")
    if _is_number(term):
        years = program in _MORTGAGE_PROGRAMS and term % 12 == 0
        head.append("{}-Year Fixed".format(_whole(term / 12)) if years else "{} Month".format(_whole(term)))
    if q.get("special"):
        head.append("Fixed")  # the site's word for a certificate special's term
    if q.get("jumbo"):
        head.append("Jumbo")
    if q.get("special") and "special" not in name.lower():
        head.append("Special")
    if q.get("branch_name"):
        head.append(title_words(q["branch_name"]))
    return ", ".join([" ".join(head + [name])] + _tiers(q))


def _value(f: Fact) -> str:
    """``value_text`` verbatim, then the attribute's unit word unless the text already names one."""
    unit, text = _UNIT_WORDS.get(f.attribute), f.value_text
    if unit is None:
        return text
    if not any(ch.isdigit() for ch in text):
        return "{} ({})".format(text, unit)  # "N/A (APY)"
    if unit.lower() in text.lower() or "annual percentage" in text.lower():
        return text  # "5.39% APR", "8.34% annual percentage rate"
    return "{} {}".format(text, unit)


def phrase(row: Row) -> str:
    """``7.13% rate (7.27% APR)``: the row's asked value, then each companion column in parentheses."""
    return _value(row[0]) + "".join(" ({})".format(_value(f)) for f in row[1:])
