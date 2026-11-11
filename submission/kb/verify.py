"""Quote checks for curated data: a quote must be on its page in its crawl, and its value must lie inside the quote.

``page_text`` is the one normalisation both sides of the substring test go through: ``[text](url)`` reduced to its
text, ``**`` and ``__`` removed, every hyphen, dash and minus variant mapped to ``-``, curly quotes straightened, and
whitespace runs (newlines and no-break spaces included) collapsed to one space. ``value_in_quote`` compares numbers
the way ``harness/scoring.py`` reads them (``normalize.number_tokens``) and text through ``normalize.norm_text``.
Standard library only; nothing here reads a file.
"""
from __future__ import annotations

import re
from typing import Optional

from .normalize import norm_text, normalize_dashes, number_tokens

_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [text](url) -> text
_EMPHASIS_RE = re.compile(r"\*\*|__")
_SPACE_RE = re.compile(r"\s+")
_QUOTES = str.maketrans({  # the same straightening normalize.norm_text applies
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
})
_DIGIT_RE = re.compile(r"[0-9]")
_ORDINAL_WORDS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                  "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
                  "eighteenth", "nineteenth", "twentieth")
# "%" or "$" anywhere, or a number or ordinal word followed by a word: "22 branch office locations", "fifth time".
_UNIT_BEARING_RE = re.compile(
    r"[%$]|(?:\b[0-9][0-9,]*(?:\.[0-9]+)?(?:st|nd|rd|th)?|\b(?:" + "|".join(_ORDINAL_WORDS) + r"))\s+[a-z]", re.I)


def page_text(markdown: Optional[str]) -> str:
    """The page (or quote) text a quote is looked up in; see the module docstring for the steps."""
    text = _LINK_RE.sub(r"\1", markdown or "")
    text = _EMPHASIS_RE.sub("", text)
    text = normalize_dashes(text).translate(_QUOTES)
    return _SPACE_RE.sub(" ", text).strip()


def quote_found(quote: Optional[str], text: str) -> bool:
    """True when the quote, through ``page_text``, is a non-empty substring of ``text``, itself a ``page_text``."""
    needle = page_text(quote)
    return bool(needle) and needle in text


def value_in_quote(value: Optional[str], quote: Optional[str]) -> bool:
    """A value with digits: its number tokens, units included, are a subset of the quote's. A value without digits:
    its ``norm_text`` is a substring of the quote's. An empty value is never inside a quote."""
    if _DIGIT_RE.search(value or ""):
        wanted = number_tokens(value)
        return bool(wanted) and wanted <= number_tokens(quote)
    folded = norm_text(value)
    return bool(folded) and folded in norm_text(quote)


def unit_bearing(value: Optional[str]) -> bool:
    """True when the value shows its unit: ``%`` or ``$``, or a number or ordinal word followed by a word."""
    return bool(_UNIT_BEARING_RE.search(value or ""))
