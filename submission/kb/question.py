"""Question canonicaliser (spec section 7.1): one member question becomes one frozen ``Query``.

Safe on any input and deterministic: a non-string question parses as empty text, the question is cut to
``max_chars`` before any regex runs, and each pattern (``lexicon.py``) runs on ``norm_text`` output (one space per
whitespace run) with no nested quantifier, so it is linear in the cut text. Products, attributes and intents come
from word tokens through dict and set lookups that walk the tokens or fixed tuples, never a set's iteration order.

- ``as_of``: the argument (``parse_as_of``) beats a question date; an argument that does not parse sets
  ``as_of_error`` and leaves ``as_of`` ``None`` (test ``as_of_error`` before using the key). Without an argument a
  question date counts (``as of May 2026``, ``in October 2026``, ``May 31, 2026``, ``05/31/2026``, ``end of June
  2026``; a bare month is its last day, ``mid-`` the 15th, ``early`` the 1st); a change question keeps its earliest.
  A month without a year takes ``reference_date``'s year (a later month too: the near future), ``None`` drops it.
- ``past`` (the resolver's contract): explicit past-value wording (``lexicon.PAST_WORDS`` and the rules beside it:
  "previous", "used to", "the old APY", "before it changed"), never a bare "was"; a change question keeps it False.
- Products: registry names and aliases plus ``SYNONYMS`` on word tokens (apostrophes dropped, ``dupaco`` skipped);
  the longest phrase wins and a named product beats weak and family words. Family words resolve by segment, and
  certificates by wording (IRA: ``ira_cert``; special/jumbo: ``cert_special``; else ``cert_regular``); IRA wording
  also makes a named personal certificate ``ira_cert`` unless an IRA product is named, and ``IRA savings`` names
  ``ira_variable``. A Title-Case word glued before a family word (``Jump Start savings``) is an unknown product, so
  ``product_id`` is ``None``.
  A registry alias ending in an attribute word is matched without it (``auto loan rates``). ARM wording, an
  ``<N>-year fixed`` term or an ``<N>-year rate`` with no product means ``mortgage_purchase``. Routing-number, phone
  and reply-hours questions resolve to ``membership``, where contact facts live. ``product_ids`` is ``product_id``
  and then the other products asked, in question order and refined as it is (``mortgage`` with refinance wording is
  the refinance product); a context product stands alone, no product gives ``()``, and a key with several products
  names them all, joined by ``+``. "X and Y <head>" names both when both halves name products (``COORDINATORS``).
- Intent: ``change``; the keyword intents (routing, url, count, address, hours, phone, status, how_to; url by the
  rules at ``lexicon.URL_WORDS``); ``yes_no`` (a leading Is/Are/Do/Does/Can/Did/Was/Has that is no polite request,
  or a value claim ending in ``?``); ``list`` (two named products, or a family word with a plural cue and no tier
  slot); else ``value``. Keywords outrank the auxiliary: "Can you repeat the routing number?" and "Is the Hy-Vee
  branch still open?" need their own templates. A lobby word is branch context; a lobby or drive-up cue asks the
  hours only without a phone word (an ``HOURS_WORDS`` word always does), and an hours question holding an
  ``OTHER_HOURS_WORDS`` word or sequence (holiday, ATM, customer service) asks the marker ``other_hours``. A bare
  ``lexicon.BRANCH_NAMES`` name in a question with no product word (a ``CONTEXT`` product's aside, an unknown
  product's not) is branch context for the status cue alone ("Is Hy-Vee still open?", "When does Hy-Vee close?"); a
  status question asks ``closure_date`` with a ``CLOSURE_DATE_WORDS`` word, else ``status``, and one naming no branch
  asks the marker ``other_hours`` unless it holds a ``STATUS_WORDS`` word and neither a ``CLOSURE_DATE_WORDS`` nor an
  other-hours word ("Is the branch open today?", "When does the branch close?"; "Which branches have closed?" lists).
- Attribute: the intent's own, else a multi-word requirement phrase (``minimum balance to earn``, ``how much do I
  need to open``; a two-word one such as ``minimum balance`` only when the question has no amount), else
  ``min_to_open`` for an amount ``to open`` with a ``NEED_WORDS`` word, no rate verb and no attribute word but a
  requirement one (``Do I need $500 to open a savings account?``; a fee, eligibility or term word keeps its own),
  else the first explicit word in ``ATTR_PRIORITY`` (its unpublished markers make the resolver refuse), else
  ``rate`` when a rate is implied or a list or value question names no attribute, else ``description`` when
  published; a how_to question for a branch or ATM asks the branch url. A value question naming a branch of a
  product that publishes ``alternatives`` (the branch) with an ``ALTERNATIVE_WORDS`` word or ``full service`` asks
  ``alternatives`` ("Which branch should Hy-Vee members use instead?").
  ``rate`` becomes the published rate column (``rate``, else ``apy``, else ``apr``; kept when none is, so the
  resolver refuses); no other attribute is remapped by what the registry publishes.
- Slots: qualifier names plus ``amount``, ``model_year`` (``model_year_range``: a written range's ends),
  ``superlative``, ``branch_name`` (a branch question also binds a bare ``lexicon.BRANCH_NAMES`` name: "the lobby hours
  in Waukee") and ``year_back`` ("in the previous year"); ``segment`` is always set (``business``
  wording, else ``personal``). ``7/1`` is the ARM program, never a term, and an unpriced program
  (``UNPRICED_PROGRAMS``) is one no fact carries; any product sets ``jumbo``.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from . import lexicon as lx
from . import qslots
from .lexicon import INTENTS, SYNONYMS
from .normalize import (bare_names, norm_text, number_tokens, parse_as_of, past_wording, polite_request,
                        question_dates, question_term)
from .qslots import Hit, attribute, keyword_intent, seq, slots
from .registry import Registry
from .fee_questions import fee_products as supported_fee_products
from .mentions import mentions as read_mentions
from .diagnostics import ResolutionTrace, capture_parse

__all__ = ["INTENTS", "SYNONYMS", "Query", "parse"]  # the vocabulary lives in lexicon.py and is re-exported here


@dataclass(frozen=True)
class Query:
    """What a question asks (intent, product, attribute, slots) and for which date."""

    intent: str
    product_id: Optional[str]
    attribute: Optional[str]
    slots: Tuple[Tuple[str, Any], ...]  # (name, value) pairs sorted by name
    as_of: Optional[str]
    as_of_error: bool
    raw_span: str  # the cut question, stripped: the only text a refusal may quote
    question_numbers: FrozenSet[Tuple[str, float]]
    canonical_key: str
    product_ids: Tuple[str, ...] = ()  # product_id, then the other products asked in question order; () when none
    # Explicit past-value wording ("the previous rate", "what it paid before it changed"): the value before the latest
    # change. Never on a bare "was" and never on a ``change`` question, whose template shows both sides already.
    past: bool = False
    as_of_end: Optional[str] = None
    change_point: bool = False
    mentions: Tuple[Tuple[Tuple[str, Any], ...], ...] = ()
    generic_rate: bool = False
    families: Tuple[str, ...] = ()


_Table = Dict[Tuple[str, ...], Hit]
_TABLES: Dict[int, Tuple[Registry, _Table]] = {}
_TYPO_WORDS: Dict[int, Dict[str, str]] = {}
_TYPO_PROTECTED = frozenset(w for value in vars(lx).values() for w in qslots.lexicon_words(value)) | {"apply", "enough", "online"}


def _tokens(text: str) -> Tuple[List[str], List[str], FrozenSet[int], FrozenSet[int]]:
    """(lowercase, original-case) word tokens: apostrophes dropped, ``Home$tart`` joined, ``dupaco`` skipped; the
    indices of the tokens written with a possessive 's ("the website's rate" gives ``websites``), and of the tokens
    right after a skipped ``dupaco`` ("on Dupaco's site" is no bare "on site")."""
    dropped = {m.start() - k for k, m in enumerate(lx.APOSTROPHE_RE.finditer(text))}  # where each stood once dropped
    flat = lx.HOMESTART_RE.sub("homestart", lx.APOSTROPHE_RE.sub("", text))  # as long as before: the indices hold
    raw = list(lx.WORD_RE.finditer(flat))
    keep = [k for k, m in enumerate(raw) if m.group().lower() not in lx.BRAND]
    kept = [raw[k] for k in keep]
    possessive = frozenset(i for i, m in enumerate(kept) if m.end() - m.start() > 1 and m.end() - 1 in dropped
                           and flat[m.end() - 1] in "sS")
    branded = frozenset(i for i, k in enumerate(keep) if k and raw[k - 1].group().lower() in lx.BRAND)
    return [m.group().lower() for m in kept], [m.group() for m in kept], possessive, branded


def _unique(items: List[str]) -> List[str]:
    return [item for i, item in enumerate(items) if item not in items[:i]]


def _phrase_table(registry: Registry) -> _Table:
    """Registry names and aliases as named products, then ``SYNONYMS`` over them, then the synonyms' plurals where
    nothing else claims the words; built once per registry object."""
    cached = _TABLES.get(id(registry))
    if cached is not None and cached[0] is registry:
        return cached[1]
    table: _Table = {}
    for alias, pid in sorted(registry.aliases().items(), key=lambda item: item[0]):
        key = tuple(_tokens(alias)[0])
        while len(key) > 1 and key[-1] in lx.ATTRIBUTE_WORDS and registry.family(pid) != "fees":
            # "auto loan rates": rates stays an attribute; "ATM fee" must not claim bare ATM.
            key = key[:-1]
        if 0 < len(key) <= lx.LONGEST:
            table.setdefault(key, ("product", lx.REMAP.get(pid, pid)))
    for phrase, hit in sorted(SYNONYMS.items(), key=lambda item: item[0]):
        table[tuple(_tokens(phrase)[0])] = hit
    for phrase, hit in sorted(SYNONYMS.items(), key=lambda item: item[0]):
        if not phrase.endswith("s"):
            table.setdefault(tuple(_tokens(phrase + "s")[0]), hit)
    _TABLES[id(registry)] = (registry, table)
    _TYPO_WORDS[id(registry)] = {w: w for alias in registry.aliases() for w in _tokens(alias)[0]}
    return table


def _match(toks: Sequence[str], table: _Table) -> List[Tuple[int, int, Hit]]:
    """Non-overlapping phrase hits as (start, size, (kind, target)) in question order: the longest phrase is taken
    first, then the stronger kind, then the earlier start."""
    found = []
    for i in range(len(toks)):
        for size in range(min(lx.LONGEST, len(toks) - i), 0, -1):
            hit = table.get(tuple(toks[i:i + size]))
            if hit is not None:
                found.append((size, lx.RANK[hit[0]], i, hit))
                break
    taken = [False] * len(toks)
    picked = []
    for size, _, start, hit in sorted(found, key=lambda f: (-f[0], f[1], f[2])):
        if not any(taken[start:start + size]):
            taken[start:start + size] = [True] * size
            picked.append((start, size, hit))
    return sorted(picked, key=lambda p: p[0])


def _named(table: _Table, phrase: Tuple[str, ...]) -> Optional[str]:
    """The product ``phrase`` names, a plural last word naming the singular too ("rewards cards"); else ``None``."""
    singular = phrase[:-1] + (phrase[-1][:-1],) if phrase[-1].endswith("s") else phrase
    hit = table.get(phrase) or table.get(singular)
    return hit[1] if hit is not None and hit[0] == "product" else None


def _pair_at(toks: Sequence[str], table: _Table, k: int) -> List[Tuple[int, int, Hit]]:
    """The two products of "X and Y <head>" around the coordinator at ``k`` when "Y <head>" and "X <head>" both name
    one (``lexicon.COORD_HEADS``; the head's earliest start and longest form, then the longest X, win), else ``[]``."""
    for h in range(k + 2, min(len(toks), k + lx.LONGEST)):
        for e in range(min(len(toks), h + 3), h, -1) if toks[h] in lx.COORD_HEADS else ():
            y = _named(table, tuple(toks[k + 1:e]))
            for j in range(max(0, k - 3), k) if y else ():
                x = _named(table, tuple(toks[j:k]) + tuple(toks[h:e]))
                if x and x != y:
                    return [(j, k - j, ("product", x)), (k + 1, e - k - 1, ("product", y))]
    return []


def _coordinated(toks: Sequence[str], table: _Table, hits: List[Tuple[int, int, Hit]]) -> List[Tuple[int, int, Hit]]:
    """``hits`` with each "X and Y <head>" pair (``_pair_at``) as two named products, replacing the hits there."""
    for k, t in enumerate(toks):
        pair = _pair_at(toks, table, k) if t in lx.COORDINATORS and k else []
        taken = {j for start, size, _ in pair for j in range(start, start + size)}
        if pair:
            hits = sorted([hit for hit in hits if not taken & set(range(hit[0], hit[0] + hit[1]))] + pair,
                          key=lambda hit: hit[0])
    return hits


def _family_product(family: str, segment: str, words: FrozenSet[str]) -> str:
    business = segment == "business"
    if family == "certificate" and words & lx.IRA_WORDS:
        return "ira_cert"
    if family == "certificate" and words & {"special", "specials", "jumbo"}:
        return "business_cert_special" if business else "cert_special"
    return lx.FAMILY_IDS[family][1 if business else 0]


def _products(hits: Sequence[Tuple[int, int, Hit]], toks: Sequence[str], otoks: Sequence[str],
              words: FrozenSet[str], segment: str) -> Tuple[List[str], bool]:
    """Named products in question order (with IRA wording and no IRA product named, a personal certificate is the IRA
    certificate). When none, or only context products (branch, membership), are named, the weak and family words
    (flagged) or else one loan-context hint follow them, and ``_core`` prefers those."""
    named = _unique([target for _, _, (kind, target) in hits if kind == "product"])
    if named and not set(named) <= lx.CONTEXT:
        if words & lx.IRA_WORDS and not set(named) & lx.IRA_PRODUCTS:
            named = _unique([lx.IRA_TWINS.get(pid, pid) for pid in named])
        return named, False
    found: List[str] = []
    family = False
    for start, _, (kind, target) in hits:
        if kind == "weak" and not (toks[start] in ("auto", "autos") and toks[start + 1:start + 2]
                                   and toks[start + 1] in lx.AUTO_COMPOUNDS):  # "auto-pay" names no auto loan
            found.append(target)
        elif kind == "family":
            prev = otoks[start - 1] if start > 1 else ""  # a sentence-initial capital names nothing
            if len(prev) > 1 and prev[0].isupper() and prev[1:].islower() and prev.lower() not in lx.KNOWN_CAPS:
                return named, False  # a Title-Case name glued to a family word: an unknown product
            found.append(_family_product(target, segment, words))
            family = True
    if not found and words & lx.LOAN_WORDS:
        found = [lx.LOAN_HINTS[t] for t in toks if t in lx.LOAN_HINTS][:1]
    return _unique(named + found), family


def _core(products: Sequence[str]) -> List[str]:
    """The products a question is about: context products dropped beside a financial one, and the generic "mortgage"
    beside a named home-lending product ("the mortgage rate on a construction loan")."""
    core = [p for p in products if p not in lx.CONTEXT]
    if "mortgage_purchase" in core and set(core) & lx.HOME_LENDING:
        core.remove("mortgage_purchase")
    return core


def _refined(pid: Optional[str], toks: Sequence[str], words: FrozenSet[str]) -> Optional[str]:
    """``mortgage_purchase`` asked with refinance wording is the refinance product (cash-out when it says so)."""
    if pid == "mortgage_purchase" and words & lx.REFI_WORDS:
        return "cash_out_refi" if seq(toks, ("cash", "out")) else "mortgage_refi"
    return pid


def _product_ids(pid: Optional[str], products: Sequence[str], toks: Sequence[str], words: FrozenSet[str],
                 registry: Registry) -> Tuple[str, ...]:
    """``pid``, then the other core products in question order, each refined as ``pid`` is and known to the registry;
    a context product stands alone (``_core`` drops it beside a financial one), and no product is ``()``."""
    if pid is None or pid in lx.CONTEXT:
        return () if pid is None else (pid,)
    ids = [pid]
    for product in _core(products):
        product = _refined(product, toks, words)
        try:
            registry.published(product)
        except KeyError:  # a synonym naming a product the registry no longer has
            continue
        if product not in ids:
            ids.append(product)
    return tuple(ids)


def _pick(intent: str, products: Sequence[str], branch_ctx: bool, reply: bool) -> Optional[str]:
    if intent in ("routing", "phone") or reply:
        return "membership"
    if intent == "count":
        return "branch_count" if branch_ctx or "branch_count" in products else (list(products) or [None])[0]
    core = _core(products)
    if intent in ("hours", "address", "status"):
        return "branch" if "branch" in products or not core else core[0]
    return (core or list(products) or [None])[0]


def parse(question: Any, as_of: Optional[str], registry: Registry, max_chars: int = 1000,
          reference_date: Optional[str] = None, trace: Optional[ResolutionTrace] = None) -> Query:
    """Canonicalise ``question`` (anything; cut to ``max_chars`` first) under the ``as_of`` contract above;
    ``reference_date`` (the newest crawl's ``YYYY-MM-DD``) gives a month written without a year its year."""
    text = question[:max(0, max_chars)] if isinstance(question, str) else ""
    s = norm_text(text)
    toks, otoks, possessive, branded = _tokens(text)
    table = _phrase_table(registry)
    toks = [t if t in _TYPO_PROTECTED else qslots.fix_typo(t, _TYPO_WORDS[id(registry)]) for t in toks]
    words = frozenset(toks)
    numbers = frozenset(number_tokens(text))
    dates = question_dates(s, reference_date)
    table = _phrase_table(registry)
    hits = _coordinated(toks, table, _match(toks, table))
    masked = {i for start, size, (kind, _) in hits if kind == "product" for i in range(start, start + size)}
    attr_words = frozenset(t for i, t in enumerate(toks) if i not in masked)
    attrs = frozenset(target for _, _, (kind, target) in hits if kind == "attribute")
    rate_at = {start for start, _, (kind, target) in hits if kind == "attribute" and target in lx.RATE_ATTRS}
    marked = [start for start, _, (kind, target) in hits if kind == "attribute" and target in lx.RATE_BEATING]
    if marked and rate_at and min(rate_at) < min(marked) and toks[0] in ("what", "whats", "which"):
        attrs = attrs - frozenset(lx.RATE_BEATING)  # "What is the APY on Share Savings, compounded monthly?" (SE4)
    segment = "business" if words & {"business", "businesses", "commercial"} else "personal"
    products, family = _products(hits, toks, otoks, words, segment)
    families = tuple(dict.fromkeys(target for _, _, (kind, target) in hits if kind == "family")) if products else ()
    for fam in families:
        if (family or any(registry.published(p) & lx.RATE_ATTRS for p in products)) and not any(registry.family(p) == fam for p in products):
            products.append(_family_product(fam, segment, words))
    family = family or bool(families)
    loan_overview = not products and bool(words & lx.LOAN_WORDS) and "all" in words and bool(attrs & lx.RATE_ATTRS)
    if loan_overview:
        products, families, family = ["auto_loan"], ("auto", "consumer_loan", "mortgage", "home_equity"), True
    branch_word = bool(words & (lx.BRANCH_WORDS | lx.LOBBY_WORDS)) or "branch" in products  # a lobby is a branch's
    branch_ctx = branch_word or bool(bare_names(s))  # a bare branch name too: "Where is Dupaco in Galena?"
    past, quiet = past_wording(toks, rate_at)
    # "Is Hy-Vee still open?": a bare branch name and no product word (a context product's aside) cue the status alone
    named = bool(bare_names(s)) and not any(kind in lx.PRODUCT_KINDS and target not in lx.CONTEXT
                                                   for _, _, (kind, target) in hits)
    branch_ctx = branch_word or named
    keyword = keyword_intent(toks, words, dates, branch_ctx, quiet, bool(rate_at), possessive, branded, named)
    if re.search(r"(?:https?://|[a-z0-9-]+\.(?:com|org|net)\b)", s) and words & {"page", "pages", "website", "site"}:
        keyword = "url"
    fee_products = [p for p in products if registry.family(p) == "fees"]
    if fee_products:
        fee_products = supported_fee_products(products, words, registry)
        products = fee_products  # keep direction; an unsupported operation cannot borrow the base amount
    if fee_products and keyword != "url" and words & {"fee", "fees", "cost", "charge", "charges", "price"}:
        products, keyword = fee_products, "value"
    reply = keyword == "hours" and bool(words & lx.REPLY_CUES) and not branch_ctx
    arm = bool(words & {"arm", "arms", "adjustable"}) or bool(lx.ARM_RE.search(s))
    term = question_term(s)
    pid = _pick(keyword, products, branch_word, reply)  # a count asks the branch count beside a branch word only
    joining = "join" in words or seq(toks, ("become", "a", "member"))
    joining_context = pid in (None, "membership", "website")  # generic website context is no destination
    if joining_context and (joining or words & {"qualifies", "qualified"}) and not (attrs - {"eligibility"}) and keyword in ("", "url", "how_to") and not ("open" in words and words & lx.NEED_WORDS):
        pid = "membership"
        keyword = keyword if keyword in ("url", "how_to") else "url" if "online" in words or words & {"apply", "link", "url"} else ""
        attrs = attrs | {"url" if keyword == "url" or keyword == "how_to" and words & {"online", "apply"} else "eligibility"}
    if keyword == "count":
        if "volunteer" in s or "volunteered" in s or "volunteering" in s or "vto" in words:
            pid = "vto_users" if "time off" in s or "vto" in words else "volunteer_hours"
        else:
            pid = next((lx.COUNT_NOUNS[t] for t in toks if t in lx.COUNT_NOUNS), pid)
    if pid is None and (arm or (term is not None and term[1] and ("fixed" in words or term[2]))):
        pid = "mortgage_purchase"  # "the 7/1 ARM", "the 30-year fixed rate", "the 15-year rate": mortgage wording
    else:
        pid = _refined(pid, toks, words)
    locator = keyword == "how_to" and pid in (None, "branch") and bool(words & lx.LOCATOR_WORDS or seq(toks, (
        "near", "me")))  # "Where can I find a branch or ATM near me?": the branch locator's url (I6)
    pid = "branch" if locator else pid
    if keyword == "url" and ("branch" in products or words & lx.LOCATOR_WORDS and not _core(products)):
        pid = "branch"
    if keyword == "url" and pid is None and "contact" in words:
        pid = "contact_page"
    if pid in ("contact_page", "rates_page", "website") and not _core(products):
        keyword = "url"
    try:
        published = registry.published(pid) if pid is not None else frozenset()
    except KeyError:  # a synonym naming a product the registry no longer has
        pid, published = None, frozenset()
    slot_map = qslots.slots(s, toks, words, pid, published, hits, segment, arm, term, "branch" in products)
    if pid in lx.DATED_COUNT_PRODUCTS:
        year = qslots.year_slot(s)
        if year:
            slot_map["year"] = year
        slot_map.pop("year_back", None)
        past = False
    if keyword:
        intent = keyword
    elif (toks and toks[0] in lx.AUX and not polite_request(toks)) or (
            s.endswith("?") and not words & lx.WH and any(unit == "%" or unit == "$" and "amount" not in slot_map for unit, _ in numbers)):
        intent = "yes_no"
    elif len(_core(products)) > 1 or (family and not any(k in slot_map for k in lx.TIER_SLOTS)
                                      and words & lx.LIST_CUES):
        intent = "list"
    else:
        intent = "value"
    shortest = 3 if "amount" in slot_map else 2  # "the APY with a minimum balance of $25,000" asks the APY
    requirement = next((target for _, size, (kind, target) in hits
                        if kind == "attribute" and size >= shortest and target in lx.REQUIREMENT_ATTRS), None)
    if (requirement is None and "amount" in slot_map and attrs <= lx.REQUIREMENT_ATTRS and seq(toks, ("to", "open"))
            and attr_words & lx.NEED_WORDS and not attr_words & lx.EARN_WORDS):
        requirement = "min_to_open"  # "Do I need $500 to open a savings account?" asks the opening minimum
    if "amount" in slot_map and "open" in words and ("enough" in words or "with" in words) and attrs <= lx.REQUIREMENT_ATTRS:
        requirement = "min_to_open"
    attribute = qslots.attribute(intent, attrs, toks, words if intent in ("status", "hours") else attr_words,
                                 published, slot_map, reply, requirement)
    if intent == "address" and words & {"atm", "atms"}:
        attribute = "atm_address"
    if len(published) == 1 and attribute is None and not attrs and (registry.family(pid) != "fees" or intent in ("value", "yes_no")):
        attribute = next(iter(published))
    attribute = "url" if locator and attribute is None else attribute
    if as_of is not None:
        resolved = parse_as_of(as_of)
        as_of_value, as_of_error = resolved, resolved is None and bool(str(as_of).strip())
    else:
        as_of_value = (min(dates) if intent == "change" else dates[0]) if dates else None
        as_of_error = False
    slots = tuple(sorted(slot_map.items(), key=lambda item: item[0]))
    ids = (pid,) if pid in lx.DATED_COUNT_PRODUCTS else _product_ids(pid, products, toks, words, registry)
    bound = read_mentions(toks, hits, pid, segment)
    if bound:
        slot_map["term_months"] = dict(bound[0])["term_months"]
        slots = tuple(sorted(slot_map.items()))
    generic_rate = attribute in lx.RATE_ATTRS and ("rate" in attrs or not attrs and bool(families) or loan_overview)
    named = "+".join(ids) if len(ids) > 1 else pid  # one product: the key is unchanged
    past = past and intent != "change"
    end = max(dates) if intent == "change" and len(set(dates)) > 1 else None
    point = intent == "change" and not dates and (s.startswith("when") or "last change" in s)
    key = f"{intent}|{named}|{attribute}|{sorted(slots)}|{as_of_value}" + ("|past" if past else "")
    key += ("|" + end if end else "") + ("|when" if point else "")
    query = Query(intent, pid, attribute, slots, as_of_value, as_of_error, text.strip(), numbers, key, ids, past, end, point,
                  bound, generic_rate, families)
    if trace is not None:
        capture_parse(trace, query, hits, attrs, keyword, requirement, toks, as_of)
    return query
