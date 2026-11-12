"""Explicit loan-table bounds survive storage and display without becoming personal verdicts."""
from __future__ import annotations

import math
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Fact

_LOWER = re.compile(r"\bas low as\b", re.I)


def column_bound(attribute: str, header: str, value: Optional[float], unit: str) -> Optional[str]:
    return ("as_low_as" if attribute in ("apr", "rate") and unit == "pct" and value is not None
            and _LOWER.search(header) else None)


def validate_bound(fact: Fact) -> None:
    if fact.rate_bound is None:
        return
    if (fact.rate_bound != "as_low_as" or fact.attribute not in ("apr", "rate") or fact.unit != "pct"
            or isinstance(fact.value, bool) or not isinstance(fact.value, (int, float))
            or not math.isfinite(fact.value) or not _LOWER.search(fact.source.quote)):
        raise ValueError("invalid or unsupported rate bound")
    from .blocks import split_blocks, table_header, table_rows
    from .extract_rules import _cell_value  # reuse exactly the extractor's footnote/number normalization
    supported = False
    for block in split_blocks(fact.source.quote, frozenset()):
        header = table_header(block)
        for row in table_rows(block):
            supported |= any(kind == fact.attribute and _cell_value(kind, cell) == (fact.value, fact.value_text, fact.unit)
                             and column_bound(kind, head, fact.value, fact.unit) == fact.rate_bound
                             for kind, head, cell in zip(row.columns, header, row.cells))
    if not supported:
        raise ValueError("rate bound lacks matching header and cell evidence")


def bounded_value(fact: Fact) -> str:
    return ("as low as " if fact.rate_bound == "as_low_as" else "") + fact.value_text
