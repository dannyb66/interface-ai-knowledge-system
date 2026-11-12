"""Bounded grammatical senses of words shared by prose and scalar financial fields."""
from __future__ import annotations

import re

from .normalize import number_tokens, norm_text, question_dates
from .source_attribution import attribution
from .lexical_index import tokens
from . import lexicon as lx
from .historical_scope import source_reference

_REQUEST_WORDS = tokens("compare comparison distinguish differ difference explain explanation describe report reported "
                       "mean meaning length long later during average example work works they their them period "
                       "candidate receive received win won choose choice buy buying arise issue end ends after "
                       "article myth duration decline disappear")


def information_intent(intent, text, published, family, attrs):
    """A narrated event is distinct from a comparison of source observations."""
    words = re.findall(r"[a-z]+", text)
    contextual = all(information_attribute(a, attrs, words, frozenset(words), published, {}) == "description"
                     for a in attrs)
    if (intent != "change" or family not in ("information", "about") or "description" not in published
            or attrs - {"description"} and not contextual):
        return intent
    cross_time = (re.search(r"\b(?:wording|content|description|requirements?|information|versions?)\b.*\bchang", text)
                  or re.search(r"\b(?:compar\w*|chang\w*|between|from)\b.*\b(?:crawls?|snapshots?|captures?)\b", text)
                  or re.search(r"\b(?:between|from|since|until)\s+(?:(?:the|early|late|end|start)\s+)?"
                               r"(?:\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text))
    if cross_time or len(re.findall(r"\bas of\b", text)) > 1:
        return intent
    narrated = source_reference(text) is not None or re.search(r"\bchanges?\s+did\b.*\b(?:make|do)\b", text)
    policy = re.search(r"\bhow (?:does|do)\b.*\b(?:compare|differ|distinguish)\b", text)
    return "value" if narrated or policy else intent


def information_attribute(chosen, attrs, toks, words, published, slots):
    """Interpret a stated prose predicate only for a non-rate informational scope.

    Publication alone never substitutes a description for an unsupported field.
    These grammatical predicates distinguish terms of office/term insurance,
    a payout's average dividend, the person explaining benefits, and a worked
    educational example's penalty warning from requests for scalar prices.
    """
    if ("description" not in published or published - {"description", "eligibility", "count"}
            or attrs - {chosen} or slots.get("term_months") is not None):
        return chosen
    words = frozenset(toks)
    text = " ".join(toks)
    if chosen == "term_months" and (re.search(r"\bterm (?:life )?(?:insurance|policies)\b", text)
            or words & {"board", "directors", "election", "elections"} and words & {"elected", "serve", "served", "terms"}):
        return "description"
    if (chosen == "dividend_rate" and "average" in words and words & {"payout", "paid", "report", "reported"}
            and not words & {"rate", "yield", "apy", "percent", "percentage"}):
        return "description"
    if chosen == "features" and "who" in words and words & {"explain", "explains", "discuss"}:
        return "description"
    if (chosen == "penalty" and "example" in words and re.search(r"\bhow\b.*\bworks?\b", text)
            and not re.search(r"\b(?:penalt\w*) (?:amount|rate|percentage)|\bhow much\b", text)):
        return "description"
    return chosen


def _without_serving_dates(text):
    """Mask only a date directly introduced by 'as of', leaving Query intact."""
    text = norm_text(text)
    spans = [(m.start(), m.end()) for pattern in (lx.NUM_DATE_RE, lx.YEAR_MONTH_RE, lx.MONTH_RE)
             for m in pattern.finditer(text) if re.search(r"\bas of\s*$", text[:m.start()])]
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " * (end - start) + text[end:]
    return text


def serving_cutoff(text, explicit=None, reference=None):
    if explicit is not None:
        return explicit
    text = norm_text(text)
    dates = [m.group() for pattern in (lx.NUM_DATE_RE, lx.YEAR_MONTH_RE, lx.MONTH_RE)
             for m in pattern.finditer(text) if re.search(r"\bas of\s*$", text[:m.start()])]
    parsed = question_dates("as of " + dates[0], reference) if len(dates) == 1 else []
    return parsed[0] if parsed else None


def explicit_prose_scope_supported(query, facts, registry):
    """A reinterpreted prose field cannot discard a numerical scope or example.

    The original numbers remain on Query and must appear in selected evidence,
    including its publication/event attribution. Query dates never authorize a
    new report year or a different example amount merely by appearing in a prompt.
    """
    if not query.prose_reinterpreted:
        return True
    if not facts:
        return False
    evidence = " ".join(f.value_text + " " + attribution(f) for f in facts)
    aliases = " ".join(a for a, pid in registry.aliases().items() if pid == query.product_id)
    scope = _without_serving_dates(query.raw_span)
    return (number_tokens(scope) <= number_tokens(evidence)
            and not tokens(scope) - tokens(evidence + " " + aliases) - _REQUEST_WORDS)


def quantified_prose_supported(query, facts):
    """A source fraction question needs a preserved typed percentage claim."""
    fraction = re.search(r"\b(?:how much of|what (?:percentage|proportion|fraction|share) of)\b", norm_text(query.raw_span))
    if query.attribute != "description" or not fraction or source_reference(query.raw_span) is None:
        return True
    return any(f.semantics is not None and f.unit == "percent" and f.value is not None for f in facts)
