"""Page typing, authority classes, business/personal segment and legacy-alias detection."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict, FrozenSet, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .config import DEFAULT_DATA_DIR
from .normalize import canonical_url as _canonical

PAGE_TYPES = ("rate_sheet", "product_page", "calculator", "blog", "newsroom", "business_resource",
              "landing_promo", "contact", "about", "pdf", "legacy_alias", "listing")

_RATE_SHEET_PATHS = frozenset({"/rates", "/business-rates"})
_LISTING_SEGMENTS = frozenset({"tag", "author", "category", "page"})
_PROMO_SLUGS = frozenset({"switch-and-earn", "earn-more", "offer-expired"})
_ABOUT_SLUGS = frozenset({"about", "membership", "careers", "community", "foundation", "financial-services",
                          "disclosures", "privacy-policy", "digital-privacy-policy"})
_PRODUCT_SLUGS = frozenset({"personal", "business", "savings-account", "savings"})
_FILE_EXT_RE = re.compile(r"\.(?:pdf|xlsx?|csv|docx?)$", re.I)
_DATED_PATH_RE = re.compile(r"^/\d{4}/\d{2}/")  # old WordPress permalinks: /2018/09/25/slug/

# Markdown cues, used only when no URL pattern decided the type.
_EFFECTIVE_CUE_RE = re.compile(r"Rates (?:are )?effective", re.I)
_RATE_HEADER_CUE_RE = re.compile(r"^\|.*(?:Dividend Rate|\bAPR\b|\bAPY\b|Annual Percentage)", re.M | re.I)
_MIN_READ_RE = re.compile(r"^\d+ min read\s*$", re.M)
_AUTHOR_LINE_RE = re.compile(r"^\[[^\]]+\]\(https?://www\.dupaco\.com/[^)\s]*/author/[^)\s]*\)\s*$", re.M)
_WRITTEN_BY_RE = re.compile(r"^Written by \[[^\]]+\]\([^)]*\)", re.M)  # legacy article byline
_DATELINE_RE = re.compile(r"DUBUQUE, Iowa")

_ALIAS_THRESHOLD = 0.95
_MIN_ALIAS_LINES = 5  # pages this small are near-identical by chance, not by copying
_BOILERPLATE: Optional[FrozenSet[str]] = None


def _url_path(url: str) -> str:
    raw = (url or "").strip()
    return urlsplit(raw if "//" in raw else "https://" + raw).path


def _is_listing(segs: Tuple[str, ...], root: int) -> bool:
    """``segs[root]`` is a section root (``newsroom``, ``blog``, ``resources``); its index and tag pages list."""
    rest = segs[root + 1:]
    return not rest or rest[0] in _LISTING_SEGMENTS


def legacy_shaped(url: str) -> bool:
    """The URL shape of an old copy: a WordPress permalink (``/YYYY/MM/...``), the ``dupacodaily`` section, or a
    trailing slash below the root. ``canonical_url`` drops that slash, so for a canonical URL (``classify``) only the
    two path shapes count; the alias pre-pass in ``kb.system`` passes the raw URL and gets all three. Raises
    ``ValueError`` for a URL ``urlsplit`` rejects."""
    path = _url_path(url).lower()
    first = next((s for s in path.split("/") if s), "")
    return bool(_DATED_PATH_RE.match(path)) or first == "dupacodaily" or (len(path) > 1 and path.endswith("/"))


def classify(url: str, markdown: str) -> str:
    """One of ``PAGE_TYPES``: URL patterns first, then markdown cues, then the path family."""
    canonical = _canonical(url)
    path = _url_path(canonical).lower()
    segs = tuple(s for s in path.split("/") if s)
    first = segs[0] if segs else ""
    if path in _RATE_SHEET_PATHS:
        return "rate_sheet"
    if first == "hubfs" or _FILE_EXT_RE.search(path):
        return "pdf"
    if legacy_shaped(canonical):
        return "legacy_alias"
    if first in ("calculators", "business-calculators"):
        return "calculator"
    if first == "contact":
        return "contact"
    if first == "newsroom":
        return "listing" if _is_listing(segs, 0) else "newsroom"
    if "blog" in segs:
        return "listing" if _is_listing(segs, segs.index("blog")) else "blog"
    if segs[:2] == ("business", "resources"):
        return "listing" if _is_listing(segs, 1) else "business_resource"
    if first == "resources":
        return "listing"
    if path.endswith("-lp") or first in _PROMO_SLUGS:
        return "landing_promo"
    if first in _ABOUT_SLUGS:
        return "about"
    md = markdown or ""
    if _EFFECTIVE_CUE_RE.search(md) and _RATE_HEADER_CUE_RE.search(md):
        return "product_page"
    if (_MIN_READ_RE.search(md) and _AUTHOR_LINE_RE.search(md)) or _WRITTEN_BY_RE.search(md):
        return "blog"
    if _DATELINE_RE.search(md):
        return "newsroom"
    if first in _PRODUCT_SLUGS:
        return "product_page"
    return "about"


@lru_cache(maxsize=1)
def _authority_table() -> Dict[str, int]:
    data = json.loads((DEFAULT_DATA_DIR / "authority.json").read_text(encoding="utf-8"))
    table = {str(k): int(v) for k, v in data["classes"].items()}
    missing = [t for t in PAGE_TYPES if t not in table]
    if missing:
        raise ValueError("authority.json has no class for page types {}".format(missing))
    return table


def authority_of(page_type: str) -> int:
    """Authority class of ``page_type`` from ``data/authority.json`` (read once per process)."""
    table = _authority_table()
    if page_type not in table:
        raise ValueError("unknown page type {!r}; expected one of {}".format(page_type, PAGE_TYPES))
    return table[page_type]


def segment_of(canonical_url: str, heading_path: Tuple[str, ...]) -> str:
    """``business`` when the URL path or any heading mentions business (any case), else ``personal``."""
    if "business" in _url_path(canonical_url).lower():
        return "business"
    return "business" if any("business" in (h or "").lower() for h in heading_path) else "personal"


def _boilerplate() -> FrozenSet[str]:
    """Lines of ``data/boilerplate.json`` (built by scripts/build_boilerplate.py). Read here rather than via
    ``kb.blocks`` to keep this module free of that dependency; a missing file filters nothing and is retried."""
    global _BOILERPLATE
    if _BOILERPLATE is None:
        path = DEFAULT_DATA_DIR / "boilerplate.json"
        if not path.exists():
            return frozenset()
        _BOILERPLATE = frozenset(json.loads(path.read_text(encoding="utf-8"))["lines"])
    return _BOILERPLATE


@lru_cache(maxsize=4096)
def _line_set(markdown: str, boilerplate: FrozenSet[str]) -> FrozenSet[str]:
    return frozenset(s for s in (line.strip() for line in markdown.split("\n")) if s and s not in boilerplate)


def is_legacy_alias(url: str, markdown: str, canonical_pages: Mapping[str, str]) -> Optional[str]:
    """The canonical URL whose non-boilerplate line set has Jaccard >= 0.95 with this page's, else ``None``.

    ``canonical_pages`` maps canonical URL to markdown and is the caller's decision of which pages are
    canonical: a page whose own canonical URL is a key is canonical itself and never an alias, so two
    near-duplicates can never alias each other. The URL shape that marks legacy copies (a trailing slash,
    ``/YYYY/MM/DD/``, ``/dupacodaily/``) survives only in the raw URL, so the caller builds that set.
    """
    own = _canonical(url)
    if own in canonical_pages:
        return None
    bp = _boilerplate()
    mine = _line_set(markdown or "", bp)
    if len(mine) < _MIN_ALIAS_LINES:
        return None
    best: Optional[Tuple[float, str]] = None
    for cand_url, cand_md in canonical_pages.items():
        theirs = _line_set(cand_md or "", bp)
        small, large = sorted((len(mine), len(theirs)))
        if small < _MIN_ALIAS_LINES or small < _ALIAS_THRESHOLD * large:
            continue  # Jaccard <= small / large, so this pair cannot reach the threshold
        score = len(mine & theirs) / len(mine | theirs)
        if score >= _ALIAS_THRESHOLD and (best is None or score > best[0] or (score == best[0] and cand_url < best[1])):
            best = (score, cand_url)
    return best[1] if best else None
