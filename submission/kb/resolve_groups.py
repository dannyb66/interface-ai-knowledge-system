"""Independent per-mention resolution, preserving the order and evidence of each answer."""
from dataclasses import replace


def resolve_mentions(q, resolve_one):
    plans = []
    for entry in q.mentions:
        own = dict(entry)
        pid = own.pop("product_id")
        slots = {k: v for k, v in q.slots if k not in ("term_months", "jumbo", "special")}
        slots.update(own)
        part = replace(q, product_id=pid, product_ids=(pid,), intent="change" if q.intent == "change" else "value", mentions=(), families=(),
                       slots=tuple(sorted(slots.items())))
        plan = resolve_one(part)
        if not plan.confident:
            return plan
        plans.append(plan)
    facts = tuple(dict.fromkeys(f for p in plans for f in p.facts))
    return replace(plans[0], intent=q.intent, question=q.raw_span, facts=facts,
                   sources=tuple(dict.fromkeys(s for p in plans for s in p.sources)),
                   permitted_values=frozenset(v for p in plans for v in p.permitted_values))
