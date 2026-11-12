"""Ingest-time source identities and canonical URL multimaps.

The organizer's Page has no manifest filename/index. Build tools retain those;
runtime identities use the supplied snapshot, URL, title, fetched_at and content.
Content SHA256 hashes UTF-8 text after CRLF/CR -> LF only (no stripping/folding).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Dict, Iterable, Sequence, Tuple

from .normalize import canonical_url
from .pagetype import legacy_shaped
from .verify import page_text, quote_found


def content_digest(markdown: str) -> str:
    return hashlib.sha256(markdown.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcePage:
    snapshot_id: str
    raw_url: str
    canonical_url: str
    markdown: str
    title: str
    fetched_at: str
    content_sha256: str
    page_id: str


def source_page(snapshot_id: str, raw_url: str, markdown: str, title: str = "", fetched_at: str = "") -> SourcePage:
    digest = content_digest(markdown)
    identity = json.dumps([snapshot_id, raw_url, title, fetched_at, digest], ensure_ascii=False, separators=(",", ":"))
    return SourcePage(snapshot_id, raw_url, canonical_url(raw_url), markdown, title, fetched_at, digest,
                      hashlib.sha256(identity.encode("utf-8")).hexdigest())


def order(page: SourcePage) -> tuple:
    return (legacy_shaped(page.raw_url), page.raw_url, page.content_sha256, page.fetched_at, page.title, page.page_id)


class SourcePages:
    """All distinct raw variants; identical duplicate records do not duplicate evidence."""
    def __init__(self, pages: Iterable[SourcePage]):
        grouped: Dict[str, Dict[str, SourcePage]] = {}
        for page in pages:
            grouped.setdefault(page.canonical_url, {})[page.page_id] = page
        self.groups = {url: tuple(sorted(values.values(), key=order)) for url, values in sorted(grouped.items())}

    def get(self, url: str, default=()) -> Tuple[SourcePage, ...]:
        return self.groups.get(canonical_url(url), default)

    def ambiguous(self, page: SourcePage) -> bool:
        same = [p for p in self.get(page.canonical_url)
                if (p.snapshot_id, p.raw_url, p.fetched_at) == (page.snapshot_id, page.raw_url, page.fetched_at)]
        return len({p.content_sha256 for p in same}) > 1

    def collision(self, url: str) -> bool:
        return len({p.content_sha256 for p in self.get(url)}) > 1

    def summary(self) -> dict:
        return {"canonical_groups": len(self.groups), "raw_variants": sum(map(len, self.groups.values())),
                "different_content_groups": sum(self.collision(url) for url in self.groups),
                "ambiguous_raw_variants": sum(self.ambiguous(p) for rows in self.groups.values() for p in rows)}


def variants(pages: Any, url: str, snapshot_id: str) -> Tuple[SourcePage, ...]:
    """Adapt the legacy canonical->markdown or canonical->(raw_url, markdown) APIs."""
    if isinstance(pages, SourcePages):
        return tuple(page for page in pages.get(url) if page.snapshot_id == snapshot_id)
    value = pages.get(canonical_url(url), pages.get(url))
    if isinstance(value, str):
        return (source_page(snapshot_id, url, value),)
    if isinstance(value, (tuple, list)) and len(value) == 2 and all(isinstance(v, str) for v in value):
        return (source_page(snapshot_id, value[0], value[1]),)
    return ()


def normalized(page: SourcePage, cache: dict, normalizer: Callable[[str], str] = page_text) -> str:
    """Only verified identical content shares normalization; a canonical URL never keys it."""
    key = ("content", page.content_sha256)
    if key not in cache:
        cache[key] = normalizer(page.markdown)
    return cache[key]


def matching(pages: Any, url: str, snapshot_id: str, quote: str, cache: dict,
             normalizer: Callable[[str], str] = page_text, pins: Sequence[Any] = (),
             exact_raw: bool = False) -> Tuple[SourcePage, ...]:
    candidates = variants(pages, url, snapshot_id)
    if pins:
        candidates = tuple(p for p in candidates if any(pin.snapshot_id == snapshot_id and pin.raw_url == p.raw_url
                           and pin.content_sha256 == p.content_sha256 for pin in pins))
    elif isinstance(pages, SourcePages):
        candidates = tuple(p for p in candidates if not pages.ambiguous(p))
    if exact_raw:
        exact = tuple(p for p in candidates if p.raw_url == url)
        # An alias is safe only when all available variants have identical content.
        candidates = exact or (candidates if len({p.content_sha256 for p in candidates}) <= 1 else ())
    return tuple(p for p in candidates if quote_found(quote, normalized(p, cache, normalizer)))
