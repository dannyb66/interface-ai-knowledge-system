"""Conservative malformed-counter checks, separate from valid zero-valued prices."""
from __future__ import annotations

import re
from typing import Optional

_NONFINITE = re.compile(r"\b(?:NaN|Infinity|Inf)\b", re.I)
_EMPTY_COUNTER = re.compile(r"^(?:members?|branches?|assets?)\s*[:|]?\s*\$?0(?:\.0+)?\+?\s*$", re.I)


def quality_reason(value_text: str, unit: str, role: str) -> Optional[str]:
    if role == "organization_fact":
        text = " ".join(value_text.split()).strip("*# ")
        if _NONFINITE.search(text):
            return "nonfinite rendered counter"
        if _EMPTY_COUNTER.fullmatch(text):
            return "empty rendered counter"
    return None
