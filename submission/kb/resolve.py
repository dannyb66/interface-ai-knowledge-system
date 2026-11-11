"""Deterministic resolver: publication-aware tiers, temporal history, and grounded answer plans."""
from __future__ import annotations

import dataclasses
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from .lexicon import BRANCH_WORDS, RATE_ATTRS
from .normalize import bare_branch, branch_name, norm_text, number_tokens
from .plans import (_CUE_RE, _DETERMINERS, _LEAD_RE, _LINK_RE, _OWNERS, _SPAN_CAP, _UNSAFE_RE, _VERB_RE, EARLIEST_NOTE,
                    Days, _bounds, _date_tokens, _name_numbers, _refusal, _refusal_span, _sources, join_notes)
from .question import Query
from .registry import SEGMENTS, Registry
from .resolve_groups import resolve_mentions
from .store import FactStore
from .temporal import cutoff, select_dated
from .tiers import (QUALIFIER_FILTERS, TIER_SELECTORS, Minimums, Selector, branch_named, current, is_number, misses,
                    named_segment, quals, select_tier, slot)
from .types import AnswerPlan, Fact

__all__ = ["EARLIEST_NOTE", "PAST", "QUALIFIER_FILTERS", "STRICT_EXTRACTORS", "Selector", "TIER_SELECTORS", "resolve",
           "select_tier"]

PAST = "past"  # the intent of a past-value plan (compose.render_past): not a parser intent
STRICT_EXTRACTORS = frozenset({"prose", "curated"})  # a plan holding their facts lints every number, bare ones too
_EARLIEST = "earliest crawl"  # FactStore.snapshot_for's note for an as_of before the first crawl
_EXACT_SLOTS = frozenset({"branch_name", "day", "intro", "jumbo", "program", "special", "term_months", "year"})
_RANGE_SLOTS = ("amount", "model_year", "latest_model_year", "superlative")  # ranges and extrema skip exact lookup
_COMPANION = {"rate": "apr"}  # a loan "rate" question also shows the APR of the same row
_MINIMUMS = {"min_to_open": "min_to_earn", "min_to_earn": "min_to_open"}
_CERT_SIBLING = {"cert_regular": "cert_special", "business_cert_regular": "business_cert_special"}  # one way only
_JUMBO_MINIMUM = "min_to_earn"  # a jumbo row's minimum to earn is the amount that earns its rate ($100,000)
_MODEL_YEARS = ("model_year_min", "model_year_max")  # the bounds a crawl may relabel (_relabelled)
_CONTACT = frozenset({"phone", "address", "lobby_hours", "driveup_hours"})  # a branch they name must be a listed one
_BRANCH = "branch"  # the product whose facts name each listed branch: contact page addresses, hours articles
_HOURS = frozenset({"lobby_hours", "driveup_hours"})  # an hours fact lists its branch for an hours question only
_DERIVED = {"status": "closure_date"}  # asked attribute -> the attribute whose facts answer it (no status fact exists)
_CLOSING = frozenset({"status", "closure_date", "alternatives"})  # a closing branch's facts list it for no contact

Pool = Tuple[str, List[Fact]]  # (product_id, current tiers)


def _published(registry: Registry, product_id: Optional[str]) -> FrozenSet[str]:
    try:
        return registry.published(product_id) if product_id is not None else frozenset()
    except KeyError:
        return frozenset()


def _asked_attribute(q: Query, registry: Registry) -> Query:
    """``q`` with an asked minimum the product does not publish read as the other minimum when that one is
    published (certificates list only the amount to earn, which is also the amount to open); unchanged otherwise,
    so a product publishing both answers the asked one."""
    other = _MINIMUMS.get(q.attribute or "")
    published = _published(registry, q.product_id)
    if other is None or q.attribute in published or other not in published:
        return q
    return dataclasses.replace(q, attribute=other)


def _named(q: Query) -> List[str]:
    """The products the question names, each once: ``product_id`` first, then the rest of the canonicaliser's
    ``product_ids`` in question order (a hand-built ``Query`` leaves them ``()``: ``product_id`` alone)."""
    ids = getattr(q, "product_ids", None) or (q.product_id,)
    named: List[str] = []
    for pid in [q.product_id] + [p for p in ids if p != q.product_id]:
        if pid is not None and pid not in named:
            named.append(pid)
    return named


def _family(registry: Registry, product_id: str, segment: Optional[str]) -> List[str]:
    """``product_id``'s family, personal first: only ``segment``'s members when the product is of ``segment``, else
    only those of the product's own segment, so the question's segment never drops a named product or swaps it for
    another segment's twin; every member when ``segment`` is None, ``[]`` for an unknown id."""
    try:
        family = registry.family(product_id)
    except KeyError:
        return []
    if family == "savings" and segment is None:
        segment = "personal"
    if segment is not None and product_id not in registry.products_in_family(family, segment):
        segment = next((s for s in sorted(SEGMENTS) if product_id in registry.products_in_family(family, s)), None)
    return registry.products_in_family(family, segment, listing=True)


def _of_segment(registry: Registry, product_id: str, segment: str) -> bool:
    try:
        return product_id in registry.products_in_family(registry.family(product_id), segment)
    except KeyError:
        return False


def _segment_missing(q: Query, registry: Registry) -> bool:
    """The question names a segment (``named_segment``) that no named product is of, and ``product_id``'s family,
    a priced one (a member publishes a rate), has no member of that segment publishing the attribute: ``business
    HELOC``. Branch, service and membership families price nothing and serve both (``business hours``)."""
    segment = named_segment(q)
    if segment is None or q.product_id is None or any(_of_segment(registry, pid, segment) for pid in _named(q)):
        return False
    try:
        family = registry.family(q.product_id)
    except KeyError:
        return False
    priced = any(_published(registry, pid) & RATE_ATTRS for pid in registry.products_in_family(family))
    offered = any(q.attribute in _published(registry, pid) for pid in registry.products_in_family(family, segment))
    return priced and not offered


def _named_branch(q: Query) -> Optional[str]:
    """The branch a question names: the canonicaliser's ``branch_name``, else (a phone question resolves to the
    membership number, which carries none) the words before ``branch``/``office``/``location`` as the canonicaliser
    reads them; branch words alone (``a branch location``) name none."""
    name = slot(q, "branch_name")
    name = str(name) if name is not None else (branch_name(norm_text(q.raw_span or "")) or bare_branch(norm_text(q.raw_span or "")))
    return None if name is None or set(name.split()) <= BRANCH_WORDS else name


def _branch_unlisted(q: Query, store: FactStore, registry: Registry, snapshot_id: str, as_of: Optional[str]) -> bool:
    """A phone, address or hours question naming a branch that no branch fact of the crawl carries (``the Mullan
    Avenue branch``): refused rather than answered with the membership number. Hours facts list their branch only
    for an hours question, so a phone question naming a branch known from an hours article alone (``the Platteville
    branch``) refuses too, and a closure article's facts never list theirs (``the Hy-Vee branch``, closed). A rate
    question's branch stays soft."""
    name = _named_branch(q) if q.attribute in _CONTACT else None
    if name is None:
        return False
    hours = q.attribute in _HOURS
    listed = [f for attribute in sorted(_published(registry, _BRANCH))
              if (hours or attribute not in _HOURS) and attribute not in _CLOSING
              for f in store.in_force(snapshot_id, _BRANCH, attribute, as_of)]
    return not branch_named(listed, name)


def _products(q: Query, registry: Registry) -> List[str]:
    """The named products that publish the attribute; for a ``list`` question each named product's family in its
    place (personal first, kept to the segment the question names when the product is of it, else to the product's
    own), so the families come in question order, each in its own order. Every product once, every named one kept."""
    segment = named_segment(q)
    out: List[str] = []
    for pid in _named(q):
        expand = registry.family(pid) in q.families and (q.intent == "list" or slot(q, "superlative"))
        for member in _family(registry, pid, segment) if expand else [pid]:
            if member not in out and _column(q, registry, member) in _published(registry, member):
                out.append(member)
    for fam in q.families:
        if q.intent == "list" or slot(q, "superlative"):
            for member in registry.products_in_family(fam, "personal" if fam == "savings" and segment is None or q.families == ("auto", "consumer_loan", "mortgage", "home_equity") else segment, listing=True):
                if member not in out and _column(q, registry, member) in _published(registry, member):
                    out.append(member)
    return out


def _column(q: Query, registry: Registry, pid: str) -> Optional[str]:
    if q.generic_rate:
        return next((a for a in ("rate", "apy", "apr") if a in _published(registry, pid)), q.attribute)
    return q.attribute


def _with_term(facts: Sequence[Fact], term: object) -> bool:
    return any(quals(f).get("term_months") == term for f in facts)


def _current_tiers(q: Query, store: FactStore, snapshot_id: str, product_id: str, as_of: Optional[str],
                   requested: Optional[str]) -> List[Fact]:
    """Publication governs dated keys; unrelated undated keys retain ordinary current-fact ranking."""
    facts = store.in_force(snapshot_id, product_id, _DERIVED.get(q.attribute or "", q.attribute), as_of)
    if facts and any(f.published_date for f in facts):
        dated = {f.key for f in facts if f.published_date}
        cut = cutoff(requested, slot(q, "year"), any("year" in quals(f) for f in facts))
        chosen = select_dated([f for f in facts if f.key in dated], cut)
        chosen += current([f for f in facts if f.key not in dated])
        by_key = {f.key: f for f in chosen}
        return [by_key[key] for key in dict.fromkeys(f.key for f in facts) if key in by_key]
    return current(facts)


def _pools(q: Query, store: FactStore, registry: Registry, snapshot_id: str, as_of: Optional[str],
           requested: Optional[str]) -> List[Pool]:
    """``(product_id, current tiers)`` per product to answer from (``_current_tiers``; ``requested`` is the date a
    dated pool is cut at, ``None`` for none). A term the regular certificate does not list but the special one does
    comes from the special certificate (``17-month CD``); the reverse never happens. The first pool is
    ``q.product_id``'s, the only one the swap replaces."""
    pools = [(pid, _current_tiers(dataclasses.replace(q, attribute=_column(q, registry, pid)), store,
                                 snapshot_id, pid, as_of, requested)) for pid in _products(q, registry)]
    term, sibling = slot(q, "term_months"), _CERT_SIBLING.get(q.product_id or "")
    if not pools or q.intent == "list" or term is None or sibling is None or slot(q, "special") is False or _with_term(pools[0][1], term):
        return pools
    if q.attribute not in _published(registry, sibling):
        return pools
    alternative = _current_tiers(q, store, snapshot_id, sibling, as_of, requested)
    if not _with_term(alternative, term):
        return pools
    return [(sibling, alternative)] + [pool for pool in pools[1:] if pool[0] != sibling]


def _qualifier_missing(q: Query, pools: Sequence[Pool]) -> bool:
    """Every product with facts misses an asked qualifier (a list skips the members that miss it)."""
    stocked = [facts for _, facts in pools if facts]
    return bool(stocked) and all(misses(q, facts) for facts in stocked)


def _exact(q: Query, pools: Sequence[Pool]) -> List[Fact]:
    """The one current fact whose qualifiers are exactly the asked ones; never for a list, a range or a
    superlative question."""
    asked = {name: value for name, value in q.slots if name in _EXACT_SLOTS}
    if q.intent == "list" or len(pools) != 1 or not asked or any(slot(q, n) is not None for n in _RANGE_SLOTS):
        return []
    return [f for f in pools[0][1] if dict(f.qualifiers) == asked][:1]


def _jumbo_minimums(q: Query, store: FactStore, snapshot_id: str, as_of: Optional[str], pool: Pool) -> Minimums:
    """Each jumbo row's minimum to earn in the crawl, by qualifiers (``select_tier`` keeps a jumbo row for an amount
    at or above it); read only when the question asks an amount and no jumbo and the pool has a jumbo row."""
    product_id, facts = pool
    if slot(q, "amount") is None or slot(q, "jumbo") is not None or not any(quals(f).get("jumbo") for f in facts):
        return {}
    return {f.qualifiers: f.value for f in current(store.in_force(snapshot_id, product_id, _JUMBO_MINIMUM, as_of))
            if quals(f).get("jumbo") and f.value is not None}


def _enumerate(q: Query, store: FactStore, snapshot_id: str, as_of: Optional[str], pools: Sequence[Pool]) -> List[Fact]:
    rows = [f for pool in pools for f in select_tier(pool[1], q, _jumbo_minimums(q, store, snapshot_id, as_of, pool))]
    if q.families == ("auto", "consumer_loan", "mortgage", "home_equity"):
        return [min([f for f in rows if f.product_id == pid and f.value is not None], key=lambda f: f.value)
                for pid in dict.fromkeys(f.product_id for f in rows) if any(f.product_id == pid and f.value is not None for f in rows)]
    if q.families and slot(q, "superlative") and rows:
        valued = [f for f in rows if f.value is not None]
        if valued:
            return [(max if slot(q, "superlative") == "highest" else min)(valued, key=lambda f: f.value)]
    return rows


def _with_companions(q: Query, store: FactStore, snapshot_id: str, as_of: Optional[str],
                     rows: Sequence[Fact]) -> List[Fact]:
    """Each row, followed for a ``rate`` question by the companion column of the same row (its APR)."""
    tiers: Dict[str, List[Fact]] = {}
    out: List[Fact] = []
    for f in rows:
        companion = _COMPANION.get(f.attribute)
        if companion is None:
            out.append(f)
            continue
        if f.product_id not in tiers:
            tiers[f.product_id] = current(store.in_force(snapshot_id, f.product_id, companion, as_of))
        out.append(f)
        out.extend([g for g in tiers[f.product_id] if g.qualifiers == f.qualifiers][:1])
    return out


def _locator(q: Query, store: FactStore, snapshot_id: str, days: Days) -> List[Fact]:
    """The branch ``url`` fact (``/contact``, the branch locator) a branch hours plan cites after its facts' own
    pages; none for any other plan. Cited only: it is never one of the plan's facts."""
    if q.intent != "hours" or q.attribute not in _HOURS:
        return []
    return current(store.in_force(snapshot_id, _BRANCH, "url", days.get(snapshot_id)))


def _plan(q: Query, store: FactStore, registry: Registry, facts: Sequence[Fact], snapshot_id: str, note: str,
          days: Days, crawl_days: Sequence[str] = ()) -> AnswerPlan:
    permitted = set(q.question_numbers) | _date_tokens(q.as_of, crawl_days)
    for f in facts:
        permitted |= number_tokens(f.value_text) | _bounds(f) | _name_numbers(registry, f.product_id)
    dated = all(f.published_date or f.event_date for f in facts)  # cut by their own dates: no earliest-crawl caveat
    cited = list(facts) + _locator(q, store, snapshot_id, days)  # an hours plan also cites the /contact locator
    return AnswerPlan(q.intent, tuple(facts), frozenset(permitted), _sources(store, cited, days), True,
                      EARLIEST_NOTE if note == _EARLIEST and not dated else None, snapshot_id, None, q.as_of,
                      question=q.raw_span, strict_numbers=any(f.extractor in STRICT_EXTRACTORS for f in facts),
                      as_of_end=q.as_of_end)


def _changed(a: Fact, b: Fact) -> bool:
    """Whether two crawls' facts of one key differ: by number when both have one (``$100,000`` and ``$100,000.00``
    are one value), else by text."""
    if a.value is not None and b.value is not None:
        return a.value != b.value
    return a.value_text != b.value_text


def _asked_years(q: Query) -> Optional[Tuple[float, float]]:
    """The model years a question asks: its written range (``model_year_range``, "the 2024-2027 model years"), else
    its one ``model_year`` as a range of one year, else ``None``."""
    span, year = slot(q, "model_year_range"), slot(q, "model_year")
    if span is not None:
        return float(span[0]), float(span[1])
    return (float(year), float(year)) if is_number(year) else None


def _relabelled(crawl: Sequence[Fact], row: Fact, asked: Optional[Tuple[float, float]] = None) -> Optional[Fact]:
    """``row``'s tier in an earlier crawl that relabelled its model years (crawl 05 made ``2023-2026`` read
    ``2024-2027``): the crawl's row of the same other qualifiers whose model years share the most years with the
    ``asked`` ones (``_asked_years``), so one asked year takes the row containing it (a 2023 car sat in the August
    2023-2026 tier, not in 2021-2022: fix round 3, F5) and an asked range the row it overlaps most (2024-2027 takes
    2023-2026: fix round 4, N2); with none asked, the row overlapping ``row``'s own years most; the first on a tie;
    ``None`` when none overlaps, or a row lacks either bound."""
    def years(f: Fact) -> Optional[Tuple[float, float]]:
        d = quals(f)
        return (d[_MODEL_YEARS[0]], d[_MODEL_YEARS[1]]) if all(is_number(d.get(n)) for n in _MODEL_YEARS) else None
    def others(f: Fact) -> Dict[str, object]:
        return {name: value for name, value in f.qualifiers if name not in _MODEL_YEARS}
    best, most, mine = None, 0.0, asked or years(row)
    for f in crawl:
        theirs = years(f)
        if mine is not None and theirs is not None and others(f) == others(row):
            shared = min(mine[1], theirs[1]) - max(mine[0], theirs[0]) + 1
            if shared > most:
                best, most = f, shared
    return best


def _past(q: Query, store: FactStore, registry: Registry, reference: str, as_of: Optional[str], note: str) -> AnswerPlan:
    """A past-value question (``Query.past``): the rows the plan answers at the reference crawl, each traced back
    through the earlier crawls, newest first, each crawl read as of its own date and skipped when it lacks the row
    (by key, else its ``_relabelled`` tier). The first crawl whose value differs gives the old value: that crawl's
    row alone, with its own companion APR. A row no earlier crawl changed keeps the first crawl that carried its key,
    then the reference row; a relabelled tier left unchanged dates nothing. A row no earlier crawl dates is dropped,
    never "unchanged" since the reference crawl itself. Refused when the reference crawl has no row or none is left;
    the plan's intent is ``past``."""
    taken_on = dict(store.snapshots())
    order = [sid for sid, _ in store.snapshots()]
    pools = _pools(q, store, registry, reference, as_of, q.as_of)
    rows = [] if _qualifier_missing(q, pools) else (_exact(q, pools) or _enumerate(q, store, reference, as_of, pools))
    days: Days = {reference: as_of}
    facts: List[Fact] = []
    dated: List[str] = []  # the crawl date each row prints
    asked = _asked_years(q)
    for row in rows:
        kept = [(reference, row)]
        for sid in reversed(order[:order.index(reference)]):
            crawl = _current_tiers(dataclasses.replace(q, attribute=row.attribute), store, sid,
                                   row.product_id, taken_on[sid], taken_on[sid])
            then = next((f for f in crawl if f.key == row.key), None) or _relabelled(crawl, row, asked)
            if then is not None and _changed(then, row):
                kept = [(sid, then)]
                break
            if then is not None and then.key == row.key:  # a relabelled tier left unchanged dates nothing
                kept = [(sid, then), (reference, row)]
        if kept[0][0] == reference:
            continue  # nothing earlier dates the row: never "unchanged" since the reference crawl itself
        for sid, f in kept:
            days.setdefault(sid, taken_on[sid])
            facts.extend(_with_companions(q, store, sid, days[sid], [f]))
        dated.append(taken_on[kept[0][0]])
    if not facts:
        return _refusal(q, reference)
    return dataclasses.replace(_plan(q, store, registry, facts, reference, note, days, dated), intent=PAST)


def _a_year_back(q: Query, store: FactStore) -> Optional[Query]:
    """``q`` as of one year before its ``as_of`` (the newest crawl's day when undated) for a question about the previous
    year (the canonicaliser's ``year_back`` slot: "in the previous year", "the prior year"; fix round 4, N4), or
    ``None`` when that day precedes the first crawl, which no crawl reaches back to."""
    crawls = store.snapshots()
    anchor = q.as_of or crawls[-1][1]
    day = "%04d%s" % (int(anchor[:4]) - 1, "-02-28" if anchor[4:10] == "-02-29" else anchor[4:10])
    return dataclasses.replace(q, as_of=day) if day >= crawls[0][1] else None


def _change(q: Query, store: FactStore, registry: Registry, first: str, as_of: Optional[str], note: str) -> AnswerPlan:
    """Resolve requested endpoints, or the last adjacent value change for each selected key."""
    taken_on = dict(store.snapshots())
    order = list(taken_on)
    start = first if q.as_of is not None else order[0]
    end = store.snapshot_for(q.as_of_end)[0] if q.as_of_end else order[-1]
    days: Days = {start: as_of, end: q.as_of_end}
    if q.change_point:
        days = {sid: taken_on[sid] for sid in order}
    found = {}
    for sid in days:
        asked = days[sid]
        requested = asked if q.change_point else q.as_of if sid == start else q.as_of_end
        pools = _pools(q, store, registry, sid, asked, requested)
        rows = [] if _qualifier_missing(q, pools) else _enumerate(q, store, sid, asked, pools)
        found[sid] = _with_companions(q, store, sid, asked, rows)
    facts = []
    if q.change_point:
        keys = dict.fromkeys(f.key for f in found[end])
        for key in keys:
            history = [(sid, next((f for f in found[sid] if f.key == key), None)) for sid in order]
            changes = [(a, b) for a, b in zip(history, history[1:]) if a[1] and b[1] and _changed(a[1], b[1])]
            present = [entry for entry in history if entry[1] is not None]
            pair = changes[-1] if changes else (present[0], present[-1])
            facts.extend(f for _, f in pair if f)
    else:
        facts = [f for rows in found.values() for f in rows]
    if not facts:
        return _refusal(q, end)
    dates = [taken_on[sid] for sid in days] + [d for d in (q.as_of, q.as_of_end) if d]
    return dataclasses.replace(_plan(q, store, registry, facts, end, note, days, dates), same_crawl=start == end)


def _withdrawn(q: Query, store: FactStore, registry: Registry, sid: str) -> AnswerPlan:
    """Only a missing current financial value that existed in an earlier crawl is withdrawn."""
    refusal = _refusal(q, sid)
    if q.intent not in ("value", "yes_no") or q.attribute not in RATE_ATTRS:
        return refusal
    for previous, day in reversed(store.snapshots()[:list(dict(store.snapshots())).index(sid)]):
        pools = _pools(q, store, registry, previous, day, day)
        rows = [] if _qualifier_missing(q, pools) else _enumerate(q, store, previous, day, pools)
        if rows:
            return dataclasses.replace(refusal, facts=tuple(rows), withdrawn=True)
    return refusal


def resolve(q: Query, store: FactStore, registry: Registry) -> AnswerPlan:
    """``_arbitrate``'s plan, refusals included, dated once: ``first_crawl``, the ``taken_on`` of the earliest crawl,
    and ``crawl_date``, that of the plan's ``snapshot_id`` (``None`` without one or before any ingest)."""
    plan, crawls = _arbitrate(q, store, registry), store.snapshots()
    return dataclasses.replace(plan, first_crawl=crawls[0][1] if crawls else None,
                               crawl_date=dict(crawls).get(plan.snapshot_id or ""))


def _arbitrate(q: Query, store: FactStore, registry: Registry) -> AnswerPlan:
    """The arbitration of the module docstring, top to bottom. ``confident`` is False only for refusal plans."""
    if q.mentions:
        return resolve_mentions(q, lambda part: _arbitrate(part, store, registry))
    q = dataclasses.replace(q, attribute=_column(q, registry, q.product_id)) if q.product_id else q
    q = _asked_attribute(q, registry)  # (1) an unpublished minimum reads as the published one
    if (q.as_of_error or q.product_id is None or q.attribute not in _published(registry, q.product_id)
            or _segment_missing(q, registry)):
        return _refusal(q, None)  # (2) malformed date, unknown product, unpublished attribute or unoffered segment
    if slot(q, "year_back") and store.snapshots():  # "in the previous year": one year back, if a crawl reaches it
        dated = _a_year_back(q, store)
        if dated is None:
            return _refusal(q, None)  # (2) a year back precedes the first crawl
        q = dated
    try:
        snapshot_id, note = store.snapshot_for(q.as_of)
    except LookupError:  # nothing ingested yet
        return _refusal(q, None)
    as_of = None if note == _EARLIEST else q.as_of  # a pre-crawl date must not drop every dated fact
    name = _named_branch(q)
    if q.attribute == "phone" and name and branch_named(store.in_force(snapshot_id, "branch", "phone", as_of), name):
        q = dataclasses.replace(q, product_id="branch", product_ids=("branch",),
                                slots=tuple(sorted(dict(q.slots, branch_name=name).items())))
    if _branch_unlisted(q, store, registry, snapshot_id, as_of):
        return _refusal(q, snapshot_id)  # (2) a contact question naming a branch no page lists
    if getattr(q, "past", False):  # the parser's explicit past cue, before change wording; a Query without it: False
        return _past(q, store, registry, snapshot_id, as_of, note)
    if q.intent == "change":
        return _change(q, store, registry, snapshot_id, as_of, note)
    pools = _pools(q, store, registry, snapshot_id, as_of, q.as_of)  # a dated pool is cut at the asked date itself
    if _qualifier_missing(q, pools):
        return _withdrawn(q, store, registry, snapshot_id)
    rows = _exact(q, pools) or _enumerate(q, store, snapshot_id, as_of, pools)  # (3) exact key, else (4) tiers
    if not rows:
        return _withdrawn(q, store, registry, snapshot_id)
    facts = _with_companions(q, store, snapshot_id, as_of, rows)
    return _plan(q, store, registry, facts, snapshot_id, note, {snapshot_id: as_of})
