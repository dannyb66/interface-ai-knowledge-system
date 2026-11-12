"""Conservative source-reference and named-location boundaries for scalar plans.

A date attached to an article identifies that article's publication. It does not
replace the serving date or verify that a planned event subsequently happened.
No additional facts or arbitrary multi-attribute plans are constructed here.
"""
from __future__ import annotations

import re
from datetime import date

from .normalize import norm_text, number_tokens

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December")
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE = re.compile(r"\b(?:" + _MONTH + r"\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(?:19|20)\d{2}|"
                   r"(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?)\b", re.I)
_SOURCE = re.compile(r"\b(?:notices?|announcements?|articles?|releases?|reports?|stor(?:y|ies)|posts?|announc(?:e|ed|es|ing))\b", re.I)
_STRONG_SOURCE = re.compile(r"\b(?:notices?|announcements?|articles?|press releases?|annual reports?|stor(?:y|ies)|blog posts?)\b", re.I)
_CAPTURE = re.compile(r"\b(?:captur\w*|crawls?|snapshots?|fetched|as of)\b", re.I)
_DATE_LINK = re.compile(r"\s*(?:(?:from|of|on|in|dated|published|issued|released)\s+)*", re.I)
_DATE_WINDOW = re.compile(r"\bbetween\s+" + _DATE.pattern + r"\s+and\s+" + _DATE.pattern
                          + r"|\bfrom\s+" + _DATE.pattern + r"\s+(?:to|through|until)\s+" + _DATE.pattern
                          + r"|\b(?:since|until|through|before|after|as of)\s+" + _DATE.pattern, re.I)
_LEADING_DATE = re.compile(r"^\s*(?:in|during)\s+" + _DATE.pattern + r"(?=\s|,|$)", re.I)
_NAMED_LAB = re.compile(r"\b((?:[a-z][a-z'-]*\s+){1,4})(?:learning|innovation)\s+lab(?:oratory)?\b", re.I)
_LOCATION_FILLER = frozenset("the a an this that its my our your their new newest dupaco in at for of to on "
                             "where is are was were what which and or about services notice announcement".split())
_CONTACT = frozenset({"address", "phone", "lobby_hours", "driveup_hours", "closure_date", "status", "alternatives"})
_PLANNED_CLOSURE = re.compile(r"\b(?:will close|last day of service will be|scheduled to close|plans? to close)\b", re.I)


def _date_prefix(text):
    if text[:4].isdigit():
        value = text
    else:
        bits = re.findall(r"[A-Za-z]+|\d+", text)
        month = next(i for i, name in enumerate(_MONTHS, 1) if name[:3].lower() == bits[0][:3].lower())
        digits = [part for part in bits[1:] if part.isdigit()]
        value = "{}-{:02d}".format(digits[-1], month)
        if len(digits) == 2:
            value += "-{:02d}".format(int(digits[0]))
    try:
        date.fromisoformat(value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""))
    except ValueError:
        return "invalid"
    return value


def _source_dates(text):
    """Explicit source-attached ``(prefix, start, end)`` date spans."""
    text = (text or "")[:1000]
    dates = list(_DATE.finditer(text))
    windows = list(_DATE_WINDOW.finditer(text))
    spans = []
    cues = list(_SOURCE.finditer(text))
    for cue in cues:
        nearby = []
        for item in dates:
            if any(window.start() <= item.start() < window.end() for window in windows):
                continue
            lo, hi = (item.end(), cue.start()) if item.end() <= cue.start() else (cue.end(), item.start())
            between = text[lo:hi]
            # A comma in a written date is inside the match; a clause separator is not.
            if (hi < lo or hi - lo > 90 or re.search(r"[?;.!]|\b(?:when|where|what|how|who|which|whether)\b|,\s*and\b", between)
                    or _CAPTURE.search(between) or _CAPTURE.search(text[max(0, item.start() - 16):item.start()])):
                continue
            if item.start() >= cue.end() and not _DATE_LINK.fullmatch(between):
                continue  # an event described after an article cue is not its publication
            nearby.append((hi - lo, item.start(), item.end(), _date_prefix(item.group())))
        if nearby:
            _, start, end, prefix = min(nearby)
            spans.append((prefix, start, end))
    return tuple(dict.fromkeys(spans))


def source_reference(text):
    """Publication ISO prefixes, ``()`` for an undated source, or ``None``.

    Only the nearest date in the source cue's clause is attached. Capture/crawl
    dates do not identify publication, and dates in a later question clause do
    not become article dates. The returned prefixes are constraints, never facts.
    """
    text = (text or "")[:1000]
    prefixes = [prefix for prefix, _, _ in _source_dates(text)]
    if prefixes:
        return tuple(dict.fromkeys(prefixes))
    if _STRONG_SOURCE.search(text) and _LEADING_DATE.search(text):
        return ("ambiguous",)  # do not erase a detached requested year or assume it dates the article
    return () if _STRONG_SOURCE.search(text) else None


def serving_date_text(text):
    """Mask only publication spans; explicit as-of/crawl dates remain parseable."""
    text = (text or "")[:1000]
    characters = list(text)
    for _, start, end in _source_dates(text):
        characters[start:end] = " " * (end - start)
    return "".join(characters)


def historical_attribution(question, fact):
    """An explicit source question's prefix, using the fact's actual metadata."""
    if source_reference(question) is None or not fact.published_date:
        return ""
    day = fact.published_date
    written = "{} {}, {}".format(_MONTHS[int(day[5:7]) - 1], int(day[8:10]), day[:4])
    return "In the source published on {}:".format(written)


def historical_numbers(question, facts):
    return set().union(*(number_tokens(historical_attribution(question, fact)) for fact in facts))


def _named_location_supported(question, facts):
    """An unknown named lab cannot borrow a generic list of branch addresses."""
    if not any(f.product_id == "branch" and f.attribute in _CONTACT for f in facts):
        return True
    for match in _NAMED_LAB.finditer(norm_text(question)):
        name = set(match.group(1).split()) - _LOCATION_FILLER
        if name and not all(name <= set(norm_text(dict(f.qualifiers).get("branch_name", "")).replace(",", "").split())
                            for f in facts if f.product_id == "branch"):
            return False
    return True


def _requested_branch_attributes(question):
    text = norm_text(question)
    requested = set()
    if re.search(r"\b(?:address|located|location)\b|\bwhere\s+(?:is|was|could i find)\b|\bfind or call\b", text):
        requested.add("address")
    if re.search(r"\b(?:phone|telephone|call)\b", text):
        requested.add("phone")
    hours = bool(re.search(r"\b(?:hours|saturday|sunday|monday|tuesday|wednesday|thursday|friday)\b|\bwhen\b.*\bopen\b", text))
    if hours:
        if "lobby" in text or not re.search(r"\bdrive[ -]?(?:up|thru|through)\b", text):
            requested.add("lobby_hours")
        if "lobby" not in text or re.search(r"\bdrive[ -]?(?:up|thru|through)\b", text):
            requested.add("driveup_hours")
    if re.search(r"\bclos(?:e|ed|ing|ure)\b", text):
        requested.add("closure_date")
    if re.search(r"\b(?:same|similar) services\b|\b(?:instead|alternatives?)\b", text):
        requested.add("alternatives")
    # Service/staffing prose is not covered by address/contact scalars.
    if re.search(r"\b(?:services|staff|staffing|onsite|on-site)\b", text) and "alternatives" not in requested:
        requested.add("description")
    return requested


def historical_scope_supported(query, facts):
    """Reject wrong publication scope and partial historical branch answers."""
    if not _named_location_supported(query.raw_span, facts):
        return False
    references = source_reference(query.raw_span)
    if references is None:
        return True
    if not facts or any(not f.published_date for f in facts):
        return False
    if references and any(not any(f.published_date.startswith(prefix) for prefix in references) for f in facts):
        return False
    if any(not any(f.published_date.startswith(prefix) for f in facts) for prefix in references):
        return False
    if any(f.product_id == "branch" for f in facts):
        required = _requested_branch_attributes(query.raw_span)
        if not required <= {f.attribute for f in facts}:
            return False
        # Current scalar routes do not define historical multi-attribute composition.
        if len(required) > 1:
            return False
    # A scalar source answer cannot silently combine distinct articles. Reviewed
    # prose preserves source identity and completeness through its own contract.
    untyped = [f for f in facts if f.semantics is None]
    return len({(f.source.canonical_url, f.published_date) for f in untyped}) <= 1


def historical_text(text, plan):
    """Attribute legacy scalar prose; typed prose already renders its own dates."""
    if not plan.facts or source_reference(plan.question) is None:
        return text
    untyped = [f for f in plan.facts if f.semantics is None]
    if not untyped:
        return text
    prefix = historical_attribution(plan.question, untyped[0])
    return prefix + " " + text if prefix else text


def historical_render_supported(text, plan):
    """Do not keep a scalar value after lint removed its publication attribution."""
    if source_reference(plan.question) is None:
        return True
    return all(historical_attribution(plan.question, fact) in text for fact in plan.facts
               if fact.semantics is None and fact.published_date)


def contact_text(fact, branch, question):
    """Scalar contact wording: an article states a listing, not live verification."""
    historical = source_reference(question) is not None
    if fact.attribute == "address":
        subject = "The {} branch".format(branch) if branch else "The address"
        verb = "address was listed as" if historical and branch else "was listed as" if historical else "is at" if branch else "is"
        return "{} {} {}".format(subject, verb, fact.value_text)
    if historical:
        return "The {} phone number was listed as {}".format(branch + " branch" if branch else "Dupaco", fact.value_text)
    return "Call {} at {}".format("the {} branch".format(branch) if branch else "Dupaco", fact.value_text)


def announcement_closure(fact):
    """Whether the selected quote, independently of its dates, states a plan."""
    return bool(_PLANNED_CLOSURE.search(fact.source.quote))
