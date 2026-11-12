"""Comparison endpoints never turn one capture into two or exceed a serving cutoff."""
from __future__ import annotations

from . import lexicon as lx
from .historical_scope import serving_date_text
from .normalize import norm_text, question_dates
from .prose_questions import serving_cutoff, _without_serving_dates


def _month_precision(text, endpoint):
    """A bare month names a period; an explicit day or month-end does not."""
    matches = [(m, bool(m.group(1) or m.group(3))) for m in lx.MONTH_RE.finditer(text)]
    matches += [(m, True) for m in lx.NUM_DATE_RE.finditer(text)]
    matches += [(m, False) for m in lx.YEAR_MONTH_RE.finditer(text)]
    precision = [precise for m, precise in matches
                 for day in question_dates("in " + m.group(), endpoint) if day[:7] == endpoint[:7]]
    return bool(precision) and not any(precision)


def comparison_window(query, store):
    taken_on = dict(store.snapshots())
    if not taken_on:
        return None
    latest = max(taken_on.values())
    limit = min(query.serving_as_of or latest, latest)
    order = [sid for sid, day in taken_on.items() if day <= limit]
    if not order:
        return None
    text = serving_date_text(norm_text(query.raw_span))
    inline = serving_cutoff(text, reference=limit)
    endpoint_text = _without_serving_dates(text) if inline else text
    if query.serving_as_of:
        dates = question_dates(endpoint_text, limit)
        begin = min(dates) if dates else None
        requested_end = max(dates) if len(set(dates)) > 1 else None
    else:
        begin = query.as_of
        requested_end = query.as_of_end
    end_day = requested_end or limit
    if end_day > limit and _month_precision(endpoint_text, end_day):
        observed = [day for day in taken_on.values() if day <= limit and day[:7] == end_day[:7]]
        if observed:
            end_day = max(observed)
    if end_day > limit or begin and (begin > end_day or begin < min(taken_on.values())):
        return None
    start = store.snapshot_for(begin)[0] if begin else order[0]
    end = store.snapshot_for(end_day)[0]
    if start not in order or end not in order or start == end:
        return None
    days = {start: begin or taken_on[start], end: end_day}
    if query.change_point:
        days = {sid: taken_on[sid] for sid in order}
    return taken_on, order, start, end, days
