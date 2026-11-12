"""Curated product registry: the hand-edited join between table-row labels and product ids.

``data/products.json`` (seeded once from ``scripts/build_registry.py``'s census, then hand-edited) holds

- ``products``: ``{product_id, family, segment, names, aliases, attributes_published}`` per product;
- ``label_rules``: ordered ``{url_pattern, section_pattern, label_pattern, product_id, qualifiers}`` entries
  (``allow_null`` optional); the first rule whose patterns all match, and whose product's ``segment`` is the
  caller's, wins;
- ``ignore``: ``{url_pattern, label_pattern, reason}`` entries (``section_pattern`` optional) for tables that
  describe no product: calculator outputs, vehicle listings, PDF tables.

Patterns are case-insensitive ``re.search`` patterns, so each carries its own anchors, and an empty pattern
matches anything. The URL pattern sees the canonical URL; the label pattern sees the row label after
``norm_text`` (dashes and curly quotes mapped, spaces collapsed, lowercased); the section pattern matches when
any heading-path element, normalised the same way, matches. A rule applies only in its product's segment, so a
business table repeating a personal label (``Share Savings``) can never resolve to the personal product.

Qualifier values are JSON scalars, ``null`` or ``"$N"`` references to the label match's groups (``"$0"`` is
the whole label). ``null`` says the row states no such value and is dropped at resolve time; it loads only for
a qualifier listed in the rule's optional ``allow_null`` (the Mortgage Rate Relief row, which publishes no
term), so a family's required qualifiers are never silently empty. References are parsed by qualifier name: ``term_months`` with ``parse_term_months`` (bare digits count
as months), ``model_year_min``/``model_year_max`` with ``parse_model_years``,
``balance_min``/``balance_max``/``loan_amount_max`` with ``parse_tier`` (an open end drops the qualifier), any
other name as the group text after ``norm_text``. A group that took no part in the match drops its qualifier;
a group that matched text its parser rejects makes the rule not apply, so a loose pattern never yields a
guessed value. Booleans (``jumbo``, ``special``, ``intro``) are always literals.

The registry never guesses a product: a row no rule and no ignore entry matches resolves to ``None`` for the
caller to count. ``load`` reads and validates the JSON once; nothing else does I/O. Standard library only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Pattern, Tuple

from .config import DEFAULT_DATA_DIR
from .normalize import norm_text, parse_model_years, parse_term_months, parse_tier
from .conditions import CONDITION_VALUES, validate_conditions

QUALIFIERS = frozenset({"term_months", "jumbo", "special", "balance_min", "balance_max", "loan_amount_max",
                        "model_year_min", "model_year_max", "program", "card", "segment", "branch_name", "day",
                        "intro", "year", "item"}) | frozenset(CONDITION_VALUES)
SEGMENTS = frozenset({"personal", "business"})
_BOOLEAN_QUALIFIERS = frozenset({"jumbo", "special", "intro"})
# Qualifiers every label rule for a product of the family must set (spec section 5, controller ruling 2).
REQUIRED_BY_FAMILY = {
    "certificate": ("jumbo", "special"),
    "mortgage": ("program", "term_months"),
    "auto": ("model_year_min", "model_year_max"),
}
_TOP_KEYS = frozenset({"_version", "products", "label_rules", "ignore"})
_PRODUCT_KEYS = frozenset({"product_id", "family", "segment", "names", "aliases", "attributes_published"})
_RULE_KEYS = frozenset({"url_pattern", "section_pattern", "label_pattern", "product_id", "qualifiers"})
_IGNORE_KEYS = frozenset({"url_pattern", "label_pattern", "reason"})
_PRODUCT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_GROUP_REF_RE = re.compile(r"^\$(\d+)$")
_NO_PARSE = object()  # a referenced group matched text its qualifier parser rejects


@dataclass(frozen=True)
class Resolution:
    """A matched rule's product id and resolved qualifiers, or an ignored row (no product, no qualifiers)."""

    product_id: Optional[str]
    qualifiers: Dict[str, Any]
    ignored: bool


@dataclass(frozen=True)
class _Matcher:
    url: Pattern[str]
    section: Optional[Pattern[str]]  # None matches any heading path, an empty one included
    label: Pattern[str]
    segment: Optional[str]  # the rule's product segment; None (ignore entries) matches either

    def match(self, canonical_url: str, headings: Tuple[str, ...], label: str,
              segment: str) -> Optional["re.Match[str]"]:
        if self.segment is not None and segment != self.segment:
            return None
        if not self.url.search(canonical_url):
            return None
        if self.section is not None and not any(self.section.search(h) for h in headings):
            return None
        return self.label.search(label)


@dataclass(frozen=True)
class _Rule:
    matcher: _Matcher
    product_id: str
    qualifiers: Tuple[Tuple[str, Any], ...]  # literals, None or "$N" references, in file order


def _check_keys(entry: Any, where: str, required: FrozenSet[str], optional: FrozenSet[str] = frozenset()) -> None:
    if not isinstance(entry, dict):
        raise ValueError("{}: expected an object, got {!r}".format(where, entry))
    missing, unknown = sorted(required - set(entry)), sorted(set(entry) - required - optional)
    if missing or unknown:
        raise ValueError("{}: missing keys {}, unknown keys {}".format(where, missing, unknown))


def _compile(raw: Any, where: str, field: str) -> Pattern[str]:
    if not isinstance(raw, str):
        raise ValueError("{}: {} must be a string, got {!r}".format(where, field, raw))
    try:
        return re.compile(raw, re.I)
    except re.error as exc:
        raise ValueError("{}: {} {!r} does not compile: {}".format(where, field, raw, exc)) from exc


def _matcher(entry: Mapping[str, Any], where: str, segment: Optional[str]) -> _Matcher:
    section = entry.get("section_pattern", "")
    return _Matcher(_compile(entry["url_pattern"], where, "url_pattern"),
                    _compile(section, where, "section_pattern") if section else None,
                    _compile(entry["label_pattern"], where, "label_pattern"), segment)


def _parse_reference(name: str, text: str) -> Any:
    """Qualifier ``name`` read from a group's text: a value, ``None`` (drop it) or ``_NO_PARSE``."""
    if name == "term_months":
        months = parse_term_months(text)
        if months is None and text.isdigit():
            months = int(text)
        return _NO_PARSE if months is None else months
    if name in ("model_year_min", "model_year_max"):
        years = parse_model_years(text)
        return _NO_PARSE if years is None else years[0 if name == "model_year_min" else 1]
    if name in ("balance_min", "balance_max", "loan_amount_max"):
        low, high = parse_tier(text)
        if low is None and high is None:
            return _NO_PARSE
        return low if name == "balance_min" else high
    return norm_text(text) or None


def _product(entry: Any, index: int) -> Dict[str, Any]:
    where = "products[{}]".format(index)
    _check_keys(entry, where, _PRODUCT_KEYS, frozenset({"in_family_lists", "page"}))
    if "in_family_lists" in entry and not isinstance(entry["in_family_lists"], bool):
        raise ValueError(where + ": in_family_lists must be boolean")
    if "page" in entry and (not isinstance(entry["page"], str) or not entry["page"].startswith("https://")):
        raise ValueError(where + ": page must be an HTTPS URL")
    pid = entry["product_id"]
    if not isinstance(pid, str) or not _PRODUCT_ID_RE.match(pid):
        raise ValueError("{}: product_id must be a snake_case string, got {!r}".format(where, pid))
    if not isinstance(entry["family"], str) or not entry["family"]:
        raise ValueError("{} ({}): family must be a non-empty string".format(where, pid))
    if entry["segment"] not in SEGMENTS:
        raise ValueError("{} ({}): segment must be one of {}".format(where, pid, sorted(SEGMENTS)))
    for field in ("names", "aliases", "attributes_published"):
        values = entry[field]
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError("{} ({}): {} must be a list of non-empty strings".format(where, pid, field))
    if not entry["names"]:
        raise ValueError("{} ({}): names must not be empty".format(where, pid))
    return entry


def _rule(entry: Any, index: int, products: Mapping[str, Mapping[str, Any]]) -> _Rule:
    where = "label_rules[{}]".format(index)
    _check_keys(entry, where, _RULE_KEYS, frozenset({"allow_null"}))
    pid = entry["product_id"]
    if pid not in products:
        raise ValueError("{}: unknown product_id {!r}".format(where, pid))
    matcher = _matcher(entry, where, products[pid]["segment"])
    qualifiers = entry["qualifiers"]
    if not isinstance(qualifiers, dict):
        raise ValueError("{}: qualifiers must be an object".format(where))
    validate_conditions(qualifiers)
    allow_null = entry.get("allow_null", [])
    if not isinstance(allow_null, list) or not all(isinstance(q, str) for q in allow_null):
        raise ValueError("{}: allow_null must be a list of qualifier names".format(where))
    stale = [q for q in allow_null if q not in qualifiers or qualifiers[q] is not None]
    if stale:
        raise ValueError("{}: allow_null lists {} but those qualifiers are not null".format(where, stale))
    for name, value in qualifiers.items():
        if name not in QUALIFIERS:
            raise ValueError("{}: unknown qualifier {!r}; expected one of {}".format(where, name, sorted(QUALIFIERS)))
        if isinstance(value, (list, dict)):
            raise ValueError("{}: qualifier {!r} must be a JSON scalar, got {!r}".format(where, name, value))
        if value is None and name not in allow_null:
            raise ValueError("{}: qualifier {!r} is null but the rule's allow_null does not list it".format(where, name))
        if name in _BOOLEAN_QUALIFIERS and not isinstance(value, bool):
            raise ValueError("{}: qualifier {!r} must be a literal boolean, got {!r}".format(where, name, value))
        ref = _GROUP_REF_RE.match(value) if isinstance(value, str) else None
        if ref and int(ref.group(1)) > matcher.label.groups:
            raise ValueError("{}: {!r} refers to group {} but label_pattern has {} groups".format(
                where, name, ref.group(1), matcher.label.groups))
    family = products[pid]["family"]
    missing = [q for q in REQUIRED_BY_FAMILY.get(family, ()) if q not in qualifiers]
    if missing:
        raise ValueError("{} ({}, family {}): missing required qualifiers {}".format(where, pid, family, missing))
    return _Rule(matcher, pid, tuple(qualifiers.items()))


def _ignore(entry: Any, index: int) -> _Matcher:
    where = "ignore[{}]".format(index)
    _check_keys(entry, where, _IGNORE_KEYS, frozenset({"section_pattern"}))
    if not isinstance(entry["reason"], str) or not entry["reason"].strip():
        raise ValueError("{}: reason must be a non-empty string".format(where))
    return _matcher(entry, where, None)


class Registry:
    """Products, ordered label rules and the ignore list of ``data/products.json``."""

    def __init__(self, version: str, products: List[Dict[str, Any]], rules: List[_Rule],
                 ignore: List[_Matcher]) -> None:
        self.version = version
        self._rules = tuple(rules)
        self._ignore = tuple(ignore)
        self._published = {p["product_id"]: frozenset(p["attributes_published"]) for p in products}
        self._names = {p["product_id"]: p["names"][0] for p in products}
        self._family = {p["product_id"]: p["family"] for p in products}
        self._segment = {p["product_id"]: p["segment"] for p in products}
        self._order = {p["product_id"]: i for i, p in enumerate(products)}
        self._listing = {p["product_id"]: p.get("in_family_lists", True) for p in products}
        self._pages = {p["product_id"]: p.get("page") for p in products}
        aliases: Dict[str, str] = {}
        for p in products:
            for alias in p["names"] + p["aliases"]:
                key = norm_text(alias)
                if aliases.get(key, p["product_id"]) != p["product_id"]:
                    raise ValueError("alias {!r} names both {} and {}".format(alias, aliases[key], p["product_id"]))
                aliases[key] = p["product_id"]
        self._aliases = aliases

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Registry:
        """Read and validate ``path`` (default ``data/products.json``); raises ``ValueError`` on bad content."""
        target = Path(path) if path is not None else DEFAULT_DATA_DIR / "products.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != _TOP_KEYS:
            raise ValueError("{}: top-level keys must be exactly {}".format(target, sorted(_TOP_KEYS)))
        if not all(isinstance(data[k], list) for k in ("products", "label_rules", "ignore")):
            raise ValueError("{}: products, label_rules and ignore must be lists".format(target))
        products = [_product(entry, i) for i, entry in enumerate(data["products"])]
        by_id: Dict[str, Dict[str, Any]] = {}
        for p in products:
            if p["product_id"] in by_id:
                raise ValueError("{}: duplicate product_id {!r}".format(target, p["product_id"]))
            by_id[p["product_id"]] = p
        rules = [_rule(entry, i, by_id) for i, entry in enumerate(data["label_rules"])]
        ignore = [_ignore(entry, i) for i, entry in enumerate(data["ignore"])]
        return cls(str(data["_version"]), products, rules, ignore)

    def resolve(self, canonical_url: str, heading_path: Tuple[str, ...], row_label: str,
                segment: str) -> Optional[Resolution]:
        """The first matching label rule's product and qualifiers, else an ignored resolution when an ignore
        entry matches, else ``None``. An empty ``row_label`` (``Term | APR`` tables) matches ``^$`` rules."""
        label = norm_text(row_label)
        headings = tuple(norm_text(h) for h in heading_path if h)
        for rule in self._rules:
            m = rule.matcher.match(canonical_url, headings, label, segment)
            if m is None:
                continue
            qualifiers = self._qualifiers(rule, m)
            if qualifiers is not None:
                return Resolution(rule.product_id, qualifiers, False)
        for matcher in self._ignore:
            if matcher.match(canonical_url, headings, label, segment) is not None:
                return Resolution(None, {}, True)
        return None

    @staticmethod
    def _qualifiers(rule: _Rule, m: "re.Match[str]") -> Optional[Dict[str, Any]]:
        out: Dict[str, Any] = {}
        for name, value in rule.qualifiers:
            ref = _GROUP_REF_RE.match(value) if isinstance(value, str) else None
            if ref is None:
                if value is not None:
                    out[name] = value
                continue
            text = m.group(int(ref.group(1)))
            if text is None:
                continue  # an optional group that took no part in the match
            parsed = _parse_reference(name, text.strip())
            if parsed is _NO_PARSE:
                return None
            if parsed is not None:
                out[name] = parsed
        return out

    def aliases(self) -> Dict[str, str]:
        """Every product name and alias, normalised with ``norm_text``, mapped to its product id."""
        return dict(self._aliases)

    def published(self, product_id: str) -> FrozenSet[str]:
        """The attributes the site publishes for ``product_id``; ``KeyError`` for an unknown id."""
        if product_id not in self._published:
            raise KeyError("unknown product_id {!r}".format(product_id))
        return self._published[product_id]

    def display_name(self, product_id: str) -> str:
        """The first of ``names`` for ``product_id``, the name answers print; ``KeyError`` for an unknown id."""
        if product_id not in self._names:
            raise KeyError("unknown product_id {!r}".format(product_id))
        return self._names[product_id]

    def family(self, product_id: str) -> str:
        """The family of ``product_id`` (``credit_card``, ``certificate`` ...); ``KeyError`` for an unknown id."""
        if product_id not in self._family:
            raise KeyError("unknown product_id {!r}".format(product_id))
        return self._family[product_id]

    def page(self, product_id: str) -> Optional[str]:
        return self._pages.get(product_id)

    def products_in_family(self, family: str, segment: Optional[str] = None, listing: bool = False) -> List[str]:
        """Ids of ``family``'s products in registry order, personal products before business ones (lists name
        personal products first), only those of ``segment`` when one is given; ``[]`` for an unknown family."""
        members = [pid for pid, fam in self._family.items() if fam == family and segment in (None, self._segment[pid])
                   and (not listing or self._listing[pid])]
        return sorted(members, key=lambda pid: (self._segment[pid] != "personal", self._order[pid]))
