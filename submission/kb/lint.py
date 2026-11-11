"""The residue strip and the number lint of member-facing text (spec section 7.5), out of ``compose.py``.

``strip_residue`` takes markdown and footnote residue out of a rendered text; ``lint`` then drops each sentence (or
line) holding a unit-bearing number (``%`` or ``$``) outside the plan's ``permitted_values``. Bare numbers are
descriptors and pass: the term in ``60-month``, model years, the ``1`` of ``1st Rate Checking``, ZIP codes, phone
digits, crawl dates. Under ``strict`` (a plan holding a prose or curated fact: ``AnswerPlan.strict_numbers``) every
number is checked, bare ones included, since a prose value's bare number (a count, a year, an hour) is the answer.
``grounded`` tells whether some fact's value survived the lint. ``compose`` re-exports ``lint`` and
``strip_residue``, and its yes/no claim reads the same ``VALUE_UNITS``.
"""
from __future__ import annotations

import re
from typing import FrozenSet, List, Sequence, Tuple

from .normalize import number_tokens
from .types import Fact

VALUE_UNITS = frozenset({"%", "$"})  # the lint and the yes/no claim read only unit-bearing numbers
_SPLIT_RE = re.compile(r"((?<=[.!?])[ \t]+|\n)")  # sentence and line ends, kept so the text rebuilds exactly
# strip_residue, in order: literal "\r\n" (or "\n", "\r") and real CR/CRLF; bold; markdown escapes ("\*", "\$");
# footnote digits glued after "%" or "% APR"/"% APY"; any markup character left; space runs.
_BREAK_RE = re.compile(r"(?:\\r)?\\n|\\r|\r\n?")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!$|<>])")
_GLUED_PCT_RE = re.compile(r"(?<=%)\d{1,2}(?![\d.,])")
_GLUED_APR_RE = re.compile(r"(%\s*AP[RY])\d{1,2}\b", re.I)
_MARKUP_RE = re.compile(r"[*{}<>]")
_SPACES_RE = re.compile(r"[ \t]{2,}")


def strip_residue(text: str) -> str:
    """Markdown and footnote residue out of member-facing text: a literal ``\\r\\n`` (or real CR/CRLF) becomes a
    space, ``**`` goes, escapes such as ``\\*`` and ``\\$`` lose the backslash, footnote digits glued after ``%``
    or ``% APR``/``% APY`` go (``4.10%2``), any ``*``, ``{``, ``}``, ``<`` or ``>`` left goes, and space runs
    collapse. Newlines (one row per line) stay."""
    s = _BREAK_RE.sub(" ", text or "").replace("**", "")
    s = _ESCAPE_RE.sub(r"\1", s)
    s = _MARKUP_RE.sub("", _GLUED_APR_RE.sub(r"\1", _GLUED_PCT_RE.sub("", s)))
    return "\n".join(_SPACES_RE.sub(" ", line).strip() for line in s.split("\n")).strip()


def lint(text: str, permitted: FrozenSet[Tuple[str, float]], strict: bool = False) -> Tuple[str, List[str]]:
    """``text`` without each sentence (or line) holding a unit-bearing number outside ``permitted``, and the
    dropped sentences, stripped. ``number_tokens`` reads the numbers exactly as the scorer does; only ``%`` and
    ``$`` values are checked, since bare numbers are descriptors (``60-month``, ``1st``, ZIP codes, dates), unless
    ``strict``, which checks every number token, bare ones included. Kept sentences keep their own separators, so a
    text with nothing to drop comes back as it was, stripped."""
    parts = _SPLIT_RE.split(text or "")
    kept: List[str] = []
    dropped: List[str] = []
    for i in range(0, len(parts), 2):
        sentence, end = parts[i], (parts[i + 1] if i + 1 < len(parts) else "")
        if {token for token in number_tokens(sentence) if strict or token[0] in VALUE_UNITS} - permitted:
            dropped.append(sentence.strip())
        else:
            kept.append(sentence + end)
    return "".join(kept).strip(), dropped


def grounded(text: str, facts: Sequence[Fact]) -> bool:
    """Whether some fact's value survived the lint (a bare ``Yes.`` or note is no answer)."""
    values = (strip_residue(f.value_text) for f in facts)
    return any(value and value in text for value in values)
