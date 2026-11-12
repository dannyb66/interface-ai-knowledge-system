"""Allow only identified decorative prose markers to differ from verified wording."""
from __future__ import annotations

import re

# Source builders may collapse a quoted Markdown block onto the preceding line.
# A greater-than comparator before a number or ordinary word is not this marker.
_QUOTED_BLOCK = re.compile(r"(^|(?<=[.!?])\s+)>\s+(?=[\"“‘'])", re.M)
_REQUIRED_MARKER = re.compile(r"(?<=\(Required\))\\\*")
_NUMBERED_HEADING = re.compile(r"(?<!\S)(#{1,6}\s+)\\\|(\d+)\\\|")


def prose_statement(text):
    """Preserve quote content and '(Required)' while dropping their display markers."""
    text = _NUMBERED_HEADING.sub(r"\1|\2|", text)
    return _REQUIRED_MARKER.sub("", _QUOTED_BLOCK.sub(r"\1", text))
