"""Dated reviewed prose explicitly attributes its source, including historical narratives."""
from __future__ import annotations

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def attribution(fact):
    if fact.semantics is None or fact.semantics.role == "fee":
        return ""
    day = fact.published_date or fact.event_date
    if not day:
        return ""
    written = "{} {}, {}".format(_MONTHS[int(day[5:7]) - 1], int(day[8:10]), day[:4])
    return "In the source published on {}:".format(written) if fact.published_date else "For the event dated {}:".format(written)
