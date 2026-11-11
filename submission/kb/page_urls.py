"""Canonical page links explicitly curated in the product registry."""
from dataclasses import replace
from .normalize import canonical_url
from .types import ClaimType, Fact, make_key


def page_url_facts(ctx, registry):
    own = canonical_url(ctx.url)
    facts = []
    for pid in dict.fromkeys(registry.aliases().values()):
        if registry.page(pid) == own:
            key = make_key(pid, "url", {})
            source = replace(ctx.source(-1, -1, own), canonical_url=own)
            facts.append(Fact(key, pid, "url", (), None, own, "text", ClaimType.ASSERTION,
                              None, None, None, source, "rules", 1.0))
    return facts
