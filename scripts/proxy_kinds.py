"""The family kinds of scripts/build_proxy_set.py (its docstring documents them): each turns a family's universe pairs
and templates into items. ``KINDS`` maps a kind's name to its function ``(ctx, family, spec, pairs) -> items``."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from proxy_kit import (Ctx, ambiguous, asked_day, branch_display, contains, day_phrase, in_split, loan_lows,
                       money, render, same_value, sha, tier_amount, trap_token, value_token)


def make_item(family: str, spec: Dict[str, Any], tpl: Dict[str, Any], key: Any, variant: str, text: str, as_of: Any,
              must: List[str], must_not: List[str]) -> dict:
    """One item; a family of weight 0 is reported but never gates: its items weigh 0 and join no group."""
    key_s = repr(key)
    h = sha(key_s + "|" + variant)[:10]  # one group per fact and variant: the family's templates share it
    category = spec["trap_category"] if must_not and spec.get("trap_category") else spec["category"]
    weight = float(spec.get("weight", 1.0))
    return {"id": "%s-%s" % (tpl["id"], h), "question": text, "as_of": as_of, "must_include": must,
            "must_not_include": must_not, "category": category, "weight": weight, "expected_sources": [],
            "group": "%s-%s" % (family, h) if weight else None, "family": family, "template": tpl["id"],
            "route": [tpl.get("intent", spec["intent"]), key[0], key[1]], "key": key_s}


def templates_for(spec: Dict[str, Any], attr: str) -> List[Dict[str, Any]]:
    return [t for t in spec.get("templates", []) if "attributes" not in t or attr in t["attributes"]]


def wanted(key: Any, spec: Dict[str, Any]) -> bool:
    names = {name for name, _ in key[2]}
    need = spec.get("require_any")
    return not names & set(spec.get("forbid", ())) and (not need or bool(names & set(need)))


def all_keys(ctx: Ctx, pid: str, attr: str) -> List[Any]:
    return sorted({key for i in range(ctx.latest + 1) for key in ctx.pool(i, pid, attr, None)}, key=repr)


def crawl_traps(ctx: Ctx, key: Any, keep: Sequence[Any]) -> List[str]:
    """Tokens of the key's facts in every crawl, in crawl order, whose value is none of ``keep``'s."""
    out: List[str] = []
    for i in range(ctx.latest + 1):
        g = ctx.pool(i, key[0], key[1], None).get(key)
        token = None if g is None or any(same_value(g, k) for k in keep) else trap_token(g)
        if token and token not in out:
            out.append(token)
    return out


TIER_QUALIFIERS = ("balance_min", "balance_max", "loan_amount_max")


def merged(must: Sequence[str], *trap_lists: Sequence[str]) -> List[str]:
    """Deduplicate traps by grader containment and reject traps contained in the correct answer tokens."""
    out: List[str] = []
    correct = " | ".join(must)
    for token in (t for traps in trap_lists for t in traps):
        if not contains(correct, token) and not any(contains(old, token) and contains(token, old) for old in out):
            out.append(token)
    return out


def sibling_traps(facts: Dict[Any, Any], key: Any, f: Any) -> List[str]:
    """The value tokens of the key's other balance or loan-amount tiers in the pool (same qualifiers otherwise) that
    differ from ``f``'s: an answer listing every tier must lose (review I1)."""
    row = tuple(p for p in key[2] if p[0] not in TIER_QUALIFIERS)
    return [t for k2 in sorted(facts, key=repr) if k2 != key and not same_value(facts[k2], f)
            and tuple(p for p in k2[2] if p[0] not in TIER_QUALIFIERS) == row for t in [value_token(facts[k2])] if t]


def kind_current(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]],
                 tiers: bool = False) -> List[dict]:
    """``current`` (and ``tier_amount`` with ``tiers``, its sibling tiers trapped too): each key in force now."""
    items = []
    for pid, attr in pairs:
        facts = ctx.pool(ctx.latest, pid, attr, None)
        lows = loan_lows(facts)
        for key in sorted(facts, key=repr):
            f, must = facts[key], value_token(facts[key])
            if must is None or not wanted(key, spec) or not in_split(key, ctx.split):
                continue
            amount = tier_amount(dict(key[2]), lows.get(key, 0.0)) if tiers else None
            if tiers and amount is None:
                continue
            extra = {"amount": money(amount)} if amount is not None else {}
            traps = crawl_traps(ctx, key, [f])
            traps = merged([must], traps, sibling_traps(facts, key, f)) if tiers else traps
            for tpl in templates_for(spec, attr):
                r = render(ctx, spec, tpl, key, extra, amount)
                if r is not None and not ambiguous(facts, key, f, *r[1:]):
                    items.append(make_item(family, spec, tpl, key, extra.get("amount", ""), r[0], None, [must], traps))
    return items


def kind_as_of(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Each value a key held before the newest crawl, asked on a day of the last crawl that held it."""
    items: List[dict] = []
    for pid, attr in pairs:
        for key in all_keys(ctx, pid, attr):
            if not wanted(key, spec) or not in_split(key, ctx.split):
                continue
            now = ctx.pool(ctx.latest, pid, attr, None).get(key)
            held = [now] if now is not None else []
            for i in range(ctx.latest - 1, -1, -1):
                f = ctx.pool(i, pid, attr, ctx.ends[i]).get(key)
                if f is None or value_token(f) is None or any(same_value(f, g) for g in held):
                    continue
                held.append(f)
                for day in ctx.candidate_days(i, key, f):
                    facts = ctx.pool(i, pid, attr, day)
                    g = facts.get(key)
                    if g is None or not same_value(g, f):
                        continue
                    batch = []
                    for tpl in templates_for(spec, attr):
                        r = render(ctx, spec, tpl, key, {"date": day_phrase(day)})
                        if r is not None and not ambiguous(facts, key, g, *r[1:]):
                            as_of = None if tpl.get("as_of", "text") == "text" else day
                            batch.append(make_item(family, spec, tpl, key, day, r[0], as_of, [value_token(g)],
                                                   crawl_traps(ctx, key, [g])))
                    if batch:
                        items.extend(batch)
                        break
    return items


def kind_contested_day(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Each older value of a key asked on the first day of its crawl's window that a later crawl's notice dates
    another value from (``Ctx.contested``, review C1), the day the other families never ask. Expects the crawl's
    value (the crawl-window convention ``FactStore.snapshot_for`` follows) and traps the others, so a change of
    convention shows in this family; give it weight 0 so it never gates."""
    items: List[dict] = []
    for pid, attr in pairs:
        for key in all_keys(ctx, pid, attr):
            if not wanted(key, spec) or not in_split(key, ctx.split):
                continue
            for i in range(ctx.latest):
                f = ctx.pool(i, pid, attr, ctx.ends[i]).get(key)
                later = [ctx.pool(j, pid, attr, None).get(key) for j in range(i + 1, ctx.latest + 1)]
                days = sorted(g.effective_date for g in later if f is not None and g is not None and g.effective_date
                              and not same_value(g, f) and ctx.days[i] < g.effective_date <= ctx.ends[i])
                facts = ctx.pool(i, pid, attr, days[0]) if days else {}
                g = facts.get(key)
                if g is None or not same_value(g, f) or value_token(g) is None:
                    continue
                for tpl in templates_for(spec, attr):
                    r = render(ctx, spec, tpl, key, {"date": day_phrase(days[0])})
                    if r is not None and not ambiguous(facts, key, g, *r[1:]):
                        as_of = None if tpl.get("as_of", "text") == "text" else days[0]
                        items.append(make_item(family, spec, tpl, key, days[0], r[0], as_of, [value_token(g)],
                                               crawl_traps(ctx, key, [g])))
    return items


def kind_change(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Each key between neighbouring crawls, including unchanged values, and from each older value to the
    newest crawl's (``to_latest``), each end asked on a candidate day of its crawl; a third crawl's value is a trap."""
    items: List[dict] = []
    last = ctx.latest
    for pid, attr in pairs:
        for key in all_keys(ctx, pid, attr):
            if not wanted(key, spec) or not in_split(key, ctx.split):
                continue
            at = [ctx.pool(i, pid, attr, ctx.ends[i]).get(key) for i in range(last + 1)]
            ok = [f is not None and value_token(f) is not None for f in at]
            spans = {"consecutive": [(i, i + 1) for i in range(last)
                                     if ok[i] and ok[i + 1]], "to_latest": []}
            held = [at[last]] if ok[last] else []
            for i in range(last - 1, -1, -1):
                if held and ok[i] and not any(same_value(at[i], g) for g in held):
                    held.append(at[i])
                    spans["to_latest"].append((i, last))
            for mode, span_list in spans.items():
                tpls = [t for t in templates_for(spec, attr) if t.get("endpoints", "consecutive") == mode]
                for i, j in span_list:
                    start, end = ctx.asked_day(i, key, at[i], False), ctx.asked_day(j, key, at[j], False)
                    if start is None or end is None:
                        continue
                    extra = {"date_from": day_phrase(start[0]), "date_to": day_phrase(end[0])}
                    for tpl in tpls:
                        r = render(ctx, spec, tpl, key, extra)
                        if r is None or ambiguous(start[1], key, start[2], *r[1:]) or \
                                ambiguous(end[1], key, end[2], *r[1:]):
                            continue
                        items.append(make_item(family, spec, tpl, key, start[0] + "|" + end[0], r[0], None,
                                               [value_token(start[2]), value_token(end[2])],
                                               crawl_traps(ctx, key, [start[2], end[2]])))
    return items


def kind_unpublished(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Each pair with no fact in the newest crawl: a question that must be refused."""
    items = []
    for pid, attr in pairs:
        key = (pid, attr, ())
        if ctx.store.by_product_attr[ctx.ids[ctx.latest]].get((pid, attr)) or not in_split(key, ctx.split):
            continue
        for tpl in templates_for(spec, attr):
            r = render(ctx, spec, tpl, key, {})
            if r is not None:
                items.append(make_item(family, spec, tpl, key, "", r[0], None, [], []))
    return items


def dated_extra(f: Any) -> Dict[str, str]:
    q = dict(f.qualifiers)
    return {"branch": branch_display(q["branch_name"]) if q.get("branch_name") else "",
            "day": asked_day(q.get("day")), "year": "%d" % q["year"] if q.get("year") is not None else ""}


def dated_traps(ctx: Ctx, f: Any, siblings: Sequence[Any]) -> List[str]:
    """Tokens of the key's other publications in any crawl and, for a key with a year, of the product's other years."""
    others = [g for i in range(ctx.latest + 1)
              for g in ctx.store.by_product_attr[ctx.ids[i]].get((f.product_id, f.attribute), [])
              if g.key == f.key and g.published_date]
    if dict(f.qualifiers).get("year") is not None:
        others += [g for g in siblings if g.key != f.key]
    if f.attribute in ("lobby_hours", "driveup_hours"):
        branch = dict(f.qualifiers).get("branch_name")
        others += [g for g in siblings if dict(g.qualifiers).get("branch_name") != branch]
    out: List[str] = []
    for g in others:
        token = None if same_value(g, f) else trap_token(g)
        if token and token not in out:
            out.append(token)
    return out


def kind_dated(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Each dated fact of the newest crawl, newest publication per key: an hours line, a closure, a count."""
    items = []
    for pid, attr in pairs:
        facts = ctx.dated(pid, attr)
        for f in sorted(facts, key=lambda g: repr(g.key)):
            must = value_token(f)
            if must is None or not wanted(f.key, spec) or not in_split(f.key, ctx.split):
                continue
            traps = merged([must], dated_traps(ctx, f, facts))
            for tpl in templates_for(spec, attr):
                r = render(ctx, spec, tpl, f.key, dated_extra(f))
                if r is not None:
                    items.append(make_item(family, spec, tpl, f.key, "", r[0], None, [must], traps))
    return items


def kind_dated_branch(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """One branch's dated facts of one attribute together (every day line of its schedule), keyed without the day."""
    items = []
    for pid, attr in pairs:
        branches: Dict[str, List[Any]] = {}
        facts = ctx.dated(pid, attr)
        for f in facts:
            name = dict(f.qualifiers).get("branch_name")
            if name:
                branches.setdefault(name, []).append(f)
        for name in sorted(branches):
            lines = sorted(branches[name], key=lambda g: (g.source.row_idx, repr(g.key)))
            key = (pid, attr, (("branch_name", name),))
            must = list(dict.fromkeys(t for t in (value_token(g) for g in lines) if t))
            if not must or not in_split(key, ctx.split):
                continue
            traps = merged(must, [t for g in lines for t in dated_traps(ctx, g, facts)])
            for tpl in templates_for(spec, attr):
                r = render(ctx, spec, tpl, key, {"branch": branch_display(name)})
                if r is not None:
                    items.append(make_item(family, spec, tpl, key, "", r[0], None, must, traps))
    return items


def kind_unlisted_branch(ctx: Ctx, family: str, spec: Dict[str, Any], pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    """Ask for hours at named branches with no published schedule for the requested attribute."""
    items = []
    for pid, attr in pairs:
        facts = ctx.store.by_product_attr[ctx.ids[ctx.latest]].get((pid, attr), [])
        listed = {dict(f.qualifiers).get("branch_name", "").split(",")[0].strip().lower() for f in facts}
        for name in sorted(spec.get("branches", [])):
            key = (pid, attr, (("branch_name", name.lower()),))
            if name.lower() in listed or not in_split(key, ctx.split):
                continue
            for tpl in templates_for(spec, attr):
                r = render(ctx, spec, tpl, key, {"branch": name})
                if r is not None:
                    items.append(make_item(family, spec, tpl, key, "", r[0], None, [], []))
    return items


from proxy_prose import kind_prose

KINDS = {"current": kind_current, "tier_amount": lambda *a: kind_current(*a, tiers=True), "as_of": kind_as_of,
         "contested_day": kind_contested_day, "change": kind_change, "unpublished": kind_unpublished,
         "dated": kind_dated, "dated_branch": kind_dated_branch, "unlisted_branch": kind_unlisted_branch,
         "prose": kind_prose}
