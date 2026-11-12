"""Expand reviewed source statements to all exact crawl/raw pins, without API keys.

The input is a local reviewed-seed JSON document, or an existing v2 catalog.
This tool never decides truth, infers eligibility, or reads evaluation questions.
Candidate output needs independent source review before installation. All draft
output should remain in ignored results/phase4 or an external private directory.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from phase4_sources import ROOT, source_crawls
from check_prose_facts import verify_entries
from kb.claim_semantics import SourcePin, semantic_revision
from kb.prose_facts import parse_prose
from kb.registry import Registry
from kb.source_pages import normalized
from kb.temporal import published_date
from kb.verify import quote_found

PROVENANCE = {"canonical_urls", "crawls", "source_pins", "_publication_scope"}


def expand(seed, crawls, cache=None):
    """Return every quote-bearing raw variant; group only identical URL sets.

    Explicit crawl restrictions are used only when replaying an existing catalog.
    Fresh reviewed seeds omit crawls, so source expansion searches the full corpus.
    """
    cache = {} if cache is None else cache
    groups = {}
    for sid, pages in sorted(crawls.items()):
        if "crawls" in seed and sid not in seed["crawls"]:
            continue
        found = [p for rows in pages.groups.values() for p in rows
                 if quote_found(seed["quote"], normalized(p, cache))]
        # A reviewed dated claim can share generic words with another program.
        # Subject/predicate context still needs independent source review: a date
        # is only a scope boundary, never evidence that the topic is the same.
        publication_scope = seed.get("_publication_scope", seed.get("published_date") if "source_pins" in seed else None)
        if publication_scope is not None:
            if publication_scope != seed.get("published_date"):
                raise ValueError("reviewed publication scope must match declared publication")
            found = [p for p in found if published_date(p.markdown) == publication_scope]
        if found:
            urls = tuple(sorted({p.canonical_url for p in found}))
            dates = {published_date(p.markdown) for p in found}
            if seed.get("published_date") is not None and len(dates) != 1:
                raise ValueError("quote crosses publication contexts; add subject/date context: " + seed["semantics"]["claim_id"])
            publication = next(iter(dates)) if seed.get("published_date") is not None else None
            group = groups.setdefault((urls, publication), {"crawls": [], "pins": set()})
            group["crawls"].append(sid)
            group["pins"].update(SourcePin(sid, p.raw_url, p.content_sha256) for p in found)
    if not groups:
        raise ValueError("no source for reviewed claim " + seed["semantics"]["claim_id"])
    result = []
    for (urls, publication), group in sorted(groups.items(), key=lambda pair: str(pair[0])):
        pins = sorted(group["pins"], key=lambda p: (p.snapshot_id, p.raw_url, p.content_sha256))
        entry = {k: v for k, v in seed.items() if k not in PROVENANCE}
        entry.update(canonical_urls=list(urls), crawls=group["crawls"], source_pins=[asdict(p) for p in pins])
        if "published_date" in seed:
            entry["published_date"] = publication
        entry["semantics"] = {**seed["semantics"], "revision": semantic_revision(
            entry["quote"], entry["value_text"], pins, entry["effective_date"])}
        result.append(entry)
    return result


def build(seeds, base, crawls, claim_groups=()):
    cache, facts, seen = {}, list(base.get("facts", [])), set()
    for seed in seeds:
        # A previously expanded catalog can repeat one claim across disjoint URL
        # sets. Preserve each crawl scope instead of silently widening a revision.
        identity = json.dumps(seed, sort_keys=True, ensure_ascii=False)
        if identity not in seen:
            facts.extend(expand(seed, crawls, cache))
            seen.add(identity)
    result = {"_version": "phase4-reviewed-candidates-v2", "_schema_version": 2, "facts": facts}
    groups = list(base.get("claim_groups", [])) + list(claim_groups)
    if groups:
        by_identity = {json.dumps(group, sort_keys=True): group for group in groups}
        # A replay preserves declaration order as part of the reviewed artifact's
        # byte identity; deduplication must not reorder immutable audit inputs.
        result["claim_groups"] = list(by_identity.values())
    return result


def write_catalog(path, data):
    """One derived claim per line keeps reviewable artifacts below 500 lines."""
    lines = ['{"_version": ' + json.dumps(data["_version"]) + ', "_schema_version": 2, "facts": [']
    lines.extend("  " + json.dumps(fact, ensure_ascii=False, sort_keys=True) +
                 ("," if i + 1 < len(data["facts"]) else "") for i, fact in enumerate(data["facts"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines.append("]")
    if "claim_groups" in data:
        lines[-1] += ', "claim_groups": ['
        lines.extend("  " + json.dumps(group, sort_keys=True) +
                     ("," if i + 1 < len(data["claim_groups"]) else "") for i, group in enumerate(data["claim_groups"]))
        lines.append("]")
    path.write_text("\n".join(lines) + "\n}\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    parser.add_argument("--products", type=Path, default=ROOT / "submission/data/products.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data = json.loads(args.seeds.read_text(encoding="utf-8"))
    seeds = [seed for seed in data["facts"] if "semantics" in seed]
    legacy = [seed for seed in data["facts"] if "semantics" not in seed]
    base = json.loads(args.base.read_text(encoding="utf-8")) if args.base else {}
    if legacy:
        base = {**base, "facts": list(base.get("facts", [])) + legacy}
    crawls = source_crawls(args.snapshots)
    catalog = build(seeds, base, crawls, data.get("claim_groups", ()))
    entries = parse_prose(catalog, Registry.load(args.products))
    report = verify_entries(entries, crawls)
    if report["failures"]:
        for failure in report["failures"]:
            print(failure, file=sys.stderr)
        return 1
    write_catalog(args.out, catalog)
    print(json.dumps({"entries": len(entries), "source_pairs": report["total"], "source_pins": report["total_pins"],
                      "source_verification": "passed", "independent_review": "required"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
