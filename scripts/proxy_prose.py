"""Curated prose/fee evaluation claims, independent of question routing or answer output.

Ordinary prose keys split by product/attribute. Eligibility's three keys all hash to proxy,
so their whole product scopes are hash-ordered and stratified, with the final scope held out.
An eligibility question always grades the complete applicable list. Recognition has one entity but multiple dated claims; those claims are
stratified by publication date (oldest proxy, newest holdout) before any scoring. A historical
claim always carries its publication cutoff as the item's as_of argument. The two splits
therefore never share a claim identity or confuse current wording with historical truth.
"""
from __future__ import annotations

from kb.registry import Registry
from kb.temporal import select_dated
from proxy_kit import in_split, sha, tidy


def recognition_claims(facts):
    dates = sorted({f.published_date for f in facts if f.published_date})
    # This singleton family cannot appear in both strict FactKey-hash partitions.
    # Assign distinct publication claims, fixed before evaluating either partition.
    return [(day, "holdout" if i == len(dates) - 1 else "proxy") for i, day in enumerate(dates)]


def eligibility_scopes(pairs):
    keys = sorted({(pid, attr, ()) for pid, attr in pairs}, key=lambda key: (sha(repr(key)), repr(key)))
    return {key: "holdout" if i == len(keys) - 1 else "proxy" for i, key in enumerate(keys)}


def _texts(facts):
    return list(dict.fromkeys(f.value_text for f in sorted(facts, key=lambda f: (
        dict(f.qualifiers).get("item", 0), f.source.row_idx, f.value_text, f.source.canonical_url))))


def kind_prose(ctx, family, spec, pairs):
    from proxy_kinds import make_item, merged, templates_for

    registry = Registry.load()
    items = []
    latest = ctx.store.by_product_attr[ctx.ids[-1]]
    for pid, attr in sorted(pairs):
        facts = list(latest.get((pid, attr), []))
        if not facts:
            continue
        key = (pid, attr, ())
        dated = [f for f in facts if f.published_date]
        if family == "recognition":
            variants = [(day, owner) for day, owner in recognition_claims(facts) if owner == ctx.split]
        elif family == "eligibility":
            variants = [(None, ctx.split)] if eligibility_scopes(pairs)[key] == ctx.split else []
        else:
            variants = [(None, ctx.split)] if in_split(key, ctx.split) else []
        for cutoff, _ in variants:
            claim_key = (pid, attr, (("publication", cutoff),)) if family == "recognition" else key
            selected = select_dated(dated, cutoff) if dated else list(ctx.pool(ctx.latest, pid, attr, None).values())
            must = _texts(selected)
            if not must:
                continue
            historical = [f for sid in ctx.ids for f in ctx.store.by_product_attr[sid].get((pid, attr), [])]
            traps = merged(must, [f.value_text for f in historical if f.value_text not in must])
            as_of = cutoff if cutoff and cutoff != max(f.published_date for f in dated) else None
            for template in templates_for(spec, attr):
                product = spec.get("names", {}).get(pid, registry.display_name(pid))
                text = tidy(template["text"].format(product=product))
                item = make_item(family, spec, template, claim_key, cutoff or "", text, as_of, must, traps)
                item["expected_sources"] = sorted({f.source.canonical_url for f in selected})
                if family == "recognition":
                    item["split_policy"] = "publication_claim"
                elif family == "eligibility":
                    item["split_policy"] = "eligibility_scope"
                items.append(item)
    return items
