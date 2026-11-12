"""Curated statements become facts only after their quote verifies in the ingested crawl."""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, FrozenSet, List, Mapping, Optional, Tuple

from .errors import KBError
from .extract_rules import SourceContext
from .normalize import canonical_url, number_tokens
from .pagetype import authority_of, classify
from .registry import QUALIFIERS, Registry
from .types import ClaimType, Fact, make_key
from .verify import page_text, quote_found, value_in_quote
from .claim_semantics import (ClaimSemantics, SourcePin, UNITS, parse_pins, semantic_revision,
                             semantics_from_dict, validate_semantics)
from .source_pages import SourcePages, matching, variants


@dataclass(frozen=True)
class ProseEntry:
    canonical_urls: Tuple[str, ...]
    crawls: Tuple[str, ...]
    quote: str
    product_id: str
    attribute: str
    qualifiers: Tuple[Tuple[str, Any], ...]
    value: Optional[float]
    value_text: str
    unit: str
    claim_type: ClaimType
    published_date: Optional[str]
    event_date: Optional[str]
    extractor: str
    effective_date: Optional[str] = None
    semantics: Optional[ClaimSemantics] = None
    source_pins: Tuple[SourcePin, ...] = ()


_V2_FIELDS = frozenset(ProseEntry.__dataclass_fields__)
_V1_FIELDS = _V2_FIELDS - {"effective_date", "semantics", "source_pins"}


def parse_prose(data: Mapping[str, Any], registry: Registry) -> List[ProseEntry]:
    """Validate provenance, attributes and the complete value text, not just its numbers."""
    if not isinstance(data, dict) or not isinstance(data.get("_version"), str) or not isinstance(data.get("facts"), list):
        raise ValueError("prose facts: expected a versioned facts array")
    schema = data.get("_schema_version", 1)
    if type(schema) is not int or schema not in (1, 2):
        raise ValueError("prose facts: unsupported schema version")
    entries, seen = [], {}
    for i, raw in enumerate(data["facts"]):
        where = "prose[{}] {}/{}".format(i, raw.get("product_id", "?"), raw.get("attribute", "?")) if isinstance(raw, dict) else "prose[{}]".format(i)
        try:
            version2 = schema == 2 and set(raw) == _V2_FIELDS
            if set(raw) != _V1_FIELDS and not version2:
                raise ValueError("missing or unknown fields")
            pid, attr = raw["product_id"], raw["attribute"]
            if attr not in registry.published(pid):
                raise ValueError("product does not publish attribute")
            urls, crawls = raw["canonical_urls"], raw["crawls"]
            if not isinstance(urls, list) or not urls or any(not isinstance(u, str) or not u.startswith("https://") or canonical_url(u) != u for u in urls):
                raise ValueError("canonical_urls must be nonempty canonical https URLs")
            if not isinstance(crawls, list) or not crawls or any(not isinstance(s, str) or not s for s in crawls):
                raise ValueError("crawls must be nonempty snapshot ids")
            if len(urls) != len(set(urls)) or len(crawls) != len(set(crawls)):
                raise ValueError("duplicate URL or crawl")
            quote, value_text = raw["quote"], raw["value_text"]
            if not isinstance(quote, str) or not isinstance(value_text, str) or not quote_found(value_text, page_text(quote)) or not value_in_quote(value_text, quote):
                raise ValueError("value_text is not inside quote")
            if not version2 and attr in ("description", "eligibility") and "%" in quote:
                raise ValueError("description/eligibility quote contains a rate")
            quals = raw["qualifiers"]
            if not isinstance(quals, dict) or set(quals) - (QUALIFIERS | {"item", "year"}):
                raise ValueError("unknown qualifier")
            if any(not isinstance(v, (str, int, float, bool)) for v in quals.values()):
                raise ValueError("qualifiers must be scalar")
            if any(k in quals and (type(quals[k]) is not int or quals[k] < 1) for k in ("item", "year")):
                raise ValueError("item and year must be positive integers")
            if raw["unit"] not in (UNITS if version2 else ("text", "usd", "count")) or raw["extractor"] != "curated":
                raise ValueError("invalid unit or extractor")
            if raw["value"] is not None and type(raw["value"]) not in (int, float):
                raise ValueError("value must be numeric or null")
            value, unit = raw["value"], raw["unit"]
            if value is not None and not math.isfinite(value):
                raise ValueError("value must be finite")
            if unit == "text" and value is not None:
                raise ValueError("a text value must be null")
            if unit in ("count", "usd") and (value is None or
                    ("$" if unit == "usd" else "", float(value)) not in number_tokens(value_text)):
                raise ValueError("numeric value and unit must match value_text")
            for field in (("published_date", "event_date", "effective_date") if version2 else ("published_date", "event_date")):
                if raw[field] is not None and (not isinstance(raw[field], str) or date.fromisoformat(raw[field]).isoformat() != raw[field]):
                    raise ValueError("invalid " + field)
            claim = ClaimType(raw["claim_type"])
            if claim not in (ClaimType.ASSERTION, ClaimType.STATUS):
                raise ValueError("invalid prose claim type")
            key = make_key(pid, attr, quals)
            semantic, pins, effective = None, (), None
            if version2:
                pins = parse_pins(raw["source_pins"], crawls, urls)
                effective = raw["effective_date"]
                semantic = semantics_from_dict(raw["semantics"])
                validate_semantics(semantic, quote, value_text, unit, value, attr)
                if semantic.revision != semantic_revision(quote, value_text, pins, effective):
                    raise ValueError("semantic revision does not match pinned source statement")
            duplicate = (page_text(quote), key)
            if seen.get(duplicate, set()) & set(crawls):
                raise ValueError("duplicate quote/product/attribute/qualifiers")
            # A page alias can appear in only some crawls. Disjoint crawl groups represent
            # the exact page sets without citing absent pages or discarding historical facts.
            seen.setdefault(duplicate, set()).update(crawls)
            entries.append(ProseEntry(tuple(urls), tuple(crawls), quote, pid, attr, key[2], raw["value"], value_text,
                                      raw["unit"], claim, raw["published_date"], raw["event_date"], "curated",
                                      effective, semantic, pins))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("{}: {}".format(where, exc)) from exc
    return entries


def load_prose(path: Path, registry: Registry) -> List[ProseEntry]:
    return parse_prose(json.loads(path.read_text(encoding="utf-8")), registry)


class ProseBook:
    """Verification is cached per page during ingest, and never runs in answer()."""
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._drops = {}

    def pages_needed(self, snapshot_id: str) -> FrozenSet[str]:
        return frozenset(u for e in self.entries if snapshot_id in e.crawls for u in e.canonical_urls)

    def facts(self, snapshot_id: str, pages: Mapping[str, Tuple[str, str]], normalized=None) -> List[Fact]:
        normalized = {} if normalized is None else normalized
        facts = []
        for i, e in enumerate(self.entries):
            if snapshot_id not in e.crawls:
                continue
            for url in e.canonical_urls:
                pins = tuple(p for p in e.source_pins if p.snapshot_id == snapshot_id and canonical_url(p.raw_url) == url)
                found = matching(pages, url, snapshot_id, e.quote, normalized, page_text, pins)
                expected = {(p.raw_url, p.content_sha256) for p in pins}
                if not found or expected and not expected <= {(p.raw_url, p.content_sha256) for p in found}:
                    why = "page missing" if not variants(pages, url, snapshot_id) else "quote/source identity missing or ambiguous"
                    self._drops[(i, url, snapshot_id)] = why
                    print(KBError("KB-E08", product_id=e.product_id, attribute=e.attribute, url=url,
                                  snapshot_id=snapshot_id, why=why), file=sys.stderr)
                    continue
                self._drops.pop((i, url, snapshot_id), None)
                for page in found:
                    page_type = classify(page.raw_url, page.markdown)
                    day = re.search(r"\d{4}-\d{2}-\d{2}", snapshot_id)
                    fetched = page.fetched_at if e.semantics is not None and page.fetched_at else day.group(0) if day else ""
                    ctx = SourceContext(page.raw_url, url, page_type, authority_of(page_type), snapshot_id, fetched)
                    source = replace(ctx.source(-2, i, e.quote), page_id=page.page_id, content_sha256=page.content_sha256,
                                     citation_url=page.raw_url if isinstance(pages, SourcePages) and pages.collision(url) else None)
                    key = make_key(e.product_id, e.attribute, dict(e.qualifiers))
                    facts.append(Fact(key, e.product_id, e.attribute, e.qualifiers, e.value, e.value_text, e.unit,
                                      e.claim_type, e.effective_date, e.event_date, e.published_date, source,
                                      "curated", 1.0, e.semantics))
        return facts

    def dropped(self, observed) -> List[Tuple[str, str]]:
        return [("{} {} @{}".format(self.entries[i].product_id, url, sid), why)
                for (i, url, sid), why in sorted(self._drops.items()) if sid in observed]
