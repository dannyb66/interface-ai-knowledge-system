"""Recognition frequency, ranking position and the event's scope are distinct."""
from __future__ import annotations

import re

from .lexical_index import tokens, _STOP
from .normalize import norm_text, number_tokens
from .prose_questions import _without_serving_dates, _REQUEST_WORDS
from .prose_verdict import _WORDS, _ORDINAL, _COUNT, _counts
from .historical_scope import serving_date_text, source_reference, _SOURCE

_RANK = re.compile(r"\brank(?:s|ed|ing|ings)?\b")
_RECOGNITION = re.compile(r"\b(?:awards?|awarded|recognitions?|recogniz(?:e|es|ed)|honou?r(?:s|ed)?)\b")
_POSITION = re.compile(r"\b(?:where|what position|what place|how high)\b.*\b(?:rank\w*|place\w*|finish\w*)\b")
_FREQUENCY = re.compile(r"\b(?:how many|number of)\s+(?:times|awards|recognitions)\b|\bhow often\b")
_RANK_VALUE = re.compile(r"\b(?:ranked|placed|rank|position)(?:\s+[a-z'-]+){0,5}\s+#?(\d[\d,]*)(?:st|nd|rd|th)?\b")
_YEAR = re.compile(r"(?<![\d$])(?:19|20)\d{2}(?!\d|\s+(?:times|awards|recognitions)\b)")
_OCCURRENCE = re.compile(r"\b(?:times?|awards?|recognitions?)$")
_COHORT_QUESTION = re.compile(r"\bhow (?:many|large)\b(?!\s+(?:times|awards|recognitions)\b)|\bsize of (?:the )?(?:recognized )?group\b")
_COHORT_VALUE = re.compile(r"\b(\d[\d,]*|" + "|".join(_WORDS) + r")\s+(?:[a-z-]+\s+){0,3}"
                          r"(?:credit unions|banks|institutions|employers|companies|organizations|projects|members|employees)\b")
_ISSUER_REQUEST = re.compile(r"\b(?:what|which) organizations?\b")
_GRAMMAR = tokens("recognition recognized recognize recognizes award awards awarded honor honored rank ranks ranked "
                  "ranking rankings named name place placed placing position finish finished number many times often total "
                  "received receive get got said time never not hasnt isnt doesnt any among article report story published")
_GRAMMAR |= tokens(" ".join(_WORDS)) | tokens("best top received give given won win say said details known")


def _years(fact):
    # A crawl/fetch timestamp is not the date of a recognition event.
    event_years = set(_YEAR.findall(fact.value_text)) | {
        str(day)[:4] for day in (fact.event_date, dict(fact.qualifiers).get("year")) if day}
    return event_years or ({fact.published_date[:4]} if fact.published_date else set())


def _specific_position(text):
    ends = [m.end() for m in _ORDINAL.finditer(text)]
    ends += [m.end() for m in _RANK_VALUE.finditer(text)
             if not re.search(r"\b(?:in|during|for)\s*$", text[:m.start(1)])]
    return any(not re.match(r"\s+(?:times?|awards?|recognitions?)\b", text[end:]) for end in ends)


def _award_claim(fact):
    text = norm_text(fact.value_text)
    return bool(_RECOGNITION.search(text) or _RANK.search(text)
                or re.search(r"\bnamed\b.{0,100}\b(?:top|best|outstanding)\b", text))


def _cohort_count(fact):
    for match in _COHORT_VALUE.finditer(norm_text(fact.value_text)):
        token = match.group(1)
        value = _WORDS[token] if token in _WORDS else int(token.replace(',', ''))
        if not 1900 <= value <= 2100 or fact.unit == 'count' and fact.value == value:
            return True
    return False


def recognition_scope_supported(query, facts, registry):
    """Require a preserved ranking claim and retain explicit award scope.

    URL vocabulary only bounds the verified source's category/provider. It never
    supplies a rank or count. Ordinary legacy count corrections keep their
    existing verdict logic; an unsupported event year still cannot be asserted.
    """
    if query.attribute not in ("description", "count"):
        return True
    text = serving_date_text(_without_serving_dates(query.raw_span))
    frequency = bool(_FREQUENCY.search(text) or _counts(text))
    if frequency and _RANK.search(text) and _specific_position(text):
        return False  # the count of all recognitions does not count one particular placement
    position = bool(_POSITION.search(text) or _RANK.search(text) and not frequency)
    counts = tuple(f for f in facts if _RECOGNITION.search(norm_text(f.value_text))
                   and any(_OCCURRENCE.search(m.group()) for m in _COUNT.finditer(f.value_text)))
    if not (position or counts or _RECOGNITION.search(text) or _RANK.search(text)):
        return True
    relevant = tuple(f for f in facts if _award_claim(f))
    if not relevant:
        return False
    cohort = bool(_COHORT_QUESTION.search(text))
    if cohort and not any(_cohort_count(f) for f in relevant):
        return False  # a qualitative badge or recognition ordinal cannot size a cohort
    if position and not any(f.semantics is not None and f.unit == "count" and f.value is not None
                            and any(float(m.group(1).replace(',', '')) == f.value for m in _RANK_VALUE.finditer(norm_text(f.value_text)))
                            and not re.search(r"\b(?:not|never|no|isnt|wasnt)\b", norm_text(f.value_text)) for f in facts):
        return False
    wanted_years = set(_YEAR.findall(text))
    dated = [_years(f) for f in relevant]
    if wanted_years and (not wanted_years <= set().union(*dated) or any(not wanted_years & years for years in dated)):
        return False
    evidence = " ".join(f.value_text + " " + f.source.quote for f in facts)
    if query.intent != "yes_no" and number_tokens(text) - {("", float(y)) for y in wanted_years} - number_tokens(evidence):
        return False
    aliases = " ".join(a for a, pid in registry.aliases().items() if pid == query.product_id)
    provenance = " ".join(f.source.canonical_url for f in facts)
    grammar = _GRAMMAR
    if not position and all(f.semantics is not None for f in facts):
        grammar |= _REQUEST_WORDS
        text = _ISSUER_REQUEST.sub(" ", text)
        if source_reference(query.raw_span) is not None:
            text = _SOURCE.sub(" ", text)
        if cohort:
            grammar |= tokens("size group cohort large institution")
    return not tokens(text) - _STOP - tokens(evidence + " " + aliases + " " + provenance) - grammar
