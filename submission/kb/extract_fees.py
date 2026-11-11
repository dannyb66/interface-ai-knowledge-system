"""Read priced schedule rows in table and plain-text versions with the same registry rules."""
from __future__ import annotations

import html
import re
from typing import List

from .extract_rules import SourceContext
from .normalize import parse_date, parse_money
from .types import ClaimType, Fact, make_key

FEE_PAGE_RE = re.compile(r"^https://www\.dupaco\.com/hubfs/dupaco-credit-union-fee-schedule")
MONEY = re.compile(r"\$[\d,]+(?:\.\d+)?")
PAR = re.compile(r"par value of a share in the credit union is\s+(\$[\d,]+(?:\.\d+)?)", re.I)
EFFECTIVE = re.compile(r"Effective\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.I)


def clean(text: str) -> str:
    return html.unescape(html.unescape(text)).replace("\\*", "*").replace("_", "").replace("afet r", "after").replace("atet mpted", "attempted").strip()


def priced_rows(markdown: str):
    """Yield (line index, label, value text, original quote), retaining priced header rows too."""
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        text = clean(line)
        match = PAR.search(text)
        if match:
            yield i, "Share par value", match.group(1), line
            continue
        if text.startswith("|"):
            cells = [c.strip() for c in text.strip("|").split("|")]
            if len(cells) < 2 or not MONEY.match(cells[1]):
                continue
            label, value = cells[:2]
        else:
            match = MONEY.search(text)
            if not match:
                continue
            label, value = text[:match.start()].strip(), text[match.start():]
            if i and (label.startswith("(") or label == "correction"):
                label = clean(lines[i - 1]) + " " + label
                line = lines[i - 1] + "\n" + line
        if not label:
            continue
        value = re.sub(r"(?<=\d)\*", " ", value)
        value = re.split(r"\s+\*", value, maxsplit=1)[0]
        yield i, label, " ".join(value.split()), line


def extract_fees(markdown: str, ctx: SourceContext, registry, boilerplate) -> List[Fact]:
    if not FEE_PAGE_RE.search(ctx.canonical_url):
        return []
    date_match = EFFECTIVE.search(clean(markdown))
    effective = parse_date(date_match.group(1)) if date_match else None
    facts = []
    for i, label, value, quote in priced_rows(markdown):
        resolution = registry.resolve(ctx.canonical_url, (), label, "personal")
        if not resolution or not resolution.product_id or registry.family(resolution.product_id) != "fees":
            continue
        pid = resolution.product_id
        key = make_key(pid, "fee", resolution.qualifiers)
        facts.append(Fact(key, pid, "fee", key[2], parse_money(value), value, "usd", ClaimType.ASSERTION,
                          effective, None, None, ctx.source(-3, i, quote), "rules", 1.0))
    return facts
