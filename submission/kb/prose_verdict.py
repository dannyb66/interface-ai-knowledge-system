"""Conservative verdicts for numeric/ordinal prose claims; the evidence supplies the answer text."""
from __future__ import annotations

import re

from .normalize import number_tokens

_ORDINALS = {word: i for i, word in enumerate(("first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
    "seventeenth", "eighteenth", "nineteenth", "twentieth"), 1)}
_CARDINALS = {word: i for i, word in enumerate(("one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty"), 1)}
_WORDS = {**_ORDINALS, **_CARDINALS}
_COUNT = re.compile(r"\b(\d[\d,]*|" + "|".join(_WORDS) + r")(?:st|nd|rd|th)?\s+(?:times?|awards?|recognitions?|participating|credit unions?|branches?|members?|employees?)\b", re.I)
_NUMBER_WORD = re.compile(r"\b(?:" + "|".join(_WORDS) + r")\b", re.I)
_ORDINAL = re.compile(r"\b(?:" + "|".join(_ORDINALS) + r"|\d+(?:st|nd|rd|th))\b", re.I)
_COMPARISON = re.compile(r"\b(?:above|below|over|under|(?:more|less|higher|lower) than|at (?:least|most))\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|no|isnt|doesnt|hasnt|isn't|doesn't|hasn't)\b", re.I)
_FILLER = frozenset("is are was were has have had does do did can could will would the a an any this that it its i we you our your dupaco dupacos for from to of in on at by about and or with get got received receive provide provides program grant awards award recognition recognized named times time".split())


def _counts(text):
    return {_WORDS[m.group(1).lower()] if m.group(1).lower() in _WORDS else int(m.group(1).replace(",", ""))
            for m in _COUNT.finditer(text)}


def _ordinals(text):
    return {_ORDINALS[token] if token in _ORDINALS else int(token[:-2])
            for token in (m.group(0).lower() for m in _ORDINAL.finditer(text))}


def _quantities(text):
    """Retain every unit and numeric claim, including words outside count-noun patterns."""
    return number_tokens(text) | {("", _WORDS[m.group(0).lower()]) for m in _NUMBER_WORD.finditer(text)}


def prose_prefix(plan, label):
    if plan.intent != "yes_no":
        return ""
    if any(f.semantics is not None for f in plan.facts):
        return ""  # word overlap cannot prove typed predicates, negation, conditions or personal eligibility
    question = plan.question or ""
    evidence = " ".join(f.value_text for f in plan.facts)
    if _COMPARISON.search(question) or _NEGATION.search(question):
        return ""  # those claims need richer semantics; state the verified evidence without an assertion
    values = number_tokens(evidence)
    units = {u for u, _ in values if u in ("$", "%")}
    claims = {token for token in number_tokens(question) if token[0] in units}
    counts, ordinals = _counts(evidence), _ordinals(evidence)
    if (claims - values or counts and _counts(question) - counts
            or ordinals and _ordinals(question) - ordinals):
        return "No. "
    if _quantities(question) - _quantities(evidence):
        return ""  # an unproved year, unit, bare number or number word cannot silently become Yes
    known = set(re.findall(r"\b[a-z]+\b", (evidence + " " + label).lower())) | _FILLER | set(_WORDS)
    substantive = set(re.findall(r"\b[a-z]+\b", question.lower())) - known
    return "" if substantive else "Yes. "
