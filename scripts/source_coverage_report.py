"""Report independently reviewed claim-set coverage separately from legacy presence.

Requirements come from a source steward's reviewed manifest, never from questions
or the candidate catalog. A complete row means every required claim is present
and source-verified in that crawl; it is not a semantic answer score or proof of
coverage for the full website. Unknown/quarantined requirements stay incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from phase4_sources import ROOT, source_crawls
from check_prose_facts import verify_entries
from kb.prose_facts import load_prose
from kb.normalize import canonical_url
from kb.claim_groups import claim_identity
from kb.registry import Registry
from kb.source_pages import matching


def matrix(requirements, available):
    rows, seen = [], set()
    for requirement in requirements:
        required = requirement["required_claim_ids"]
        if not required or len(required) != len(set(required)) or any(not isinstance(c, str) or not c.strip() for c in required):
            raise ValueError("required claim set must have distinct, nonempty claim IDs")
        for sid in requirement["crawls"]:
            identity = (requirement["entity"], requirement["attribute"], requirement["claim_set"], sid)
            if identity in seen:
                raise ValueError("duplicate required claim-set row")
            seen.add(identity)
            present = available.get((identity[0], identity[1], sid), set())
            missing = sorted(set(required) - present)
            complete = not missing and requirement.get("disposition", "reviewed") == "reviewed"
            rows.append({"entity": identity[0], "attribute": identity[1], "claim_set": identity[2], "crawl": sid,
                         "required_claim_ids": required, "verified_claim_ids": sorted(set(required) & present),
                         "missing_claim_ids": missing, "complete": complete,
                         "disposition": requirement.get("disposition", "reviewed"),
                         "unknown_details": requirement.get("unknown_details", [])})
    return sorted(rows, key=lambda r: (r["entity"], r["attribute"], r["claim_set"], r["crawl"]))


def availability(entries, crawls):
    available, cache = {}, {}
    for entry in entries:
        for sid in entry.crawls:
            pages = crawls.get(sid)
            if pages is None:
                continue
            good = True
            for url in entry.canonical_urls:
                found = matching(pages, url, sid, entry.quote, cache, pins=entry.source_pins)
                actual = {(p.raw_url, p.content_sha256) for p in found}
                expected = {(p.raw_url, p.content_sha256) for p in entry.source_pins if p.snapshot_id == sid
                            and canonical_url(p.raw_url) == url}
                if not found or expected - actual:
                    good = False
            if good:
                available.setdefault((entry.product_id, entry.attribute, sid), set()).add(claim_identity(entry))
    return available


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "submission/data/prose_facts.json")
    parser.add_argument("--products", type=Path, default=ROOT / "submission/data/products.json")
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", type=Path, help="Independent attestation bound to all three input file hashes")
    args = parser.parse_args(argv)
    expected = json.loads(args.requirements.read_text(encoding="utf-8"))
    audited = False
    if args.audit:
        attestation = json.loads(args.audit.read_text(encoding="utf-8"))
        inputs = (args.requirements, args.catalog, args.products)
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        audited = (attestation.get("status") == "passed" and attestation.get("independent") is True
                   and attestation.get("artifact_sha256") == hashes)
        if not audited:
            raise ValueError("independent audit does not attest to these exact requirements/catalog/products")
    entries = load_prose(args.catalog, Registry.load(args.products))
    crawls = source_crawls(args.snapshots)
    verified = verify_entries(entries, crawls)
    available = availability(entries, crawls)
    rows = matrix(expected["requirements"], available)
    latest = sorted(crawls)[-1]
    legacy = set(expected["legacy_product_ids"])
    legacy_present = {p for p, a, sid in available if sid == latest and a in ("description", "eligibility")}
    descriptions = {p for p, a, sid in available if sid == latest and a == "description"}
    by_attribute = {}
    for attr in sorted({r["attribute"] for r in rows}):
        selected = [r for r in rows if r["attribute"] == attr]
        by_attribute[attr] = {"complete": sum(r["complete"] for r in selected), "total": len(selected)}
    summary = {"schema": "source-coverage-v1", "source_verification_passed": not verified["failures"],
               "reviewed_claim_sets": {"complete": sum(r["complete"] for r in rows), "total": len(rows)},
               "by_attribute": by_attribute,
               "legacy_presence": {"covered": len(legacy & legacy_present), "total": len(legacy)},
               "legacy_descriptions": {"covered": len(legacy & descriptions), "total": len(legacy)},
               "source_variants_by_crawl": {sid: pages.summary() for sid, pages in crawls.items()},
               "quality_decisions": expected.get("quality_decisions", []),
               "independent_review": "passed" if audited else "pending", "provisional": not audited,
               "semantic_score": None, "scope": "reviewed source requirements only; not all website claims"}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "matrix.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("source_verification_passed", "reviewed_claim_sets", "by_attribute",
                                             "legacy_presence", "legacy_descriptions", "independent_review")}, sort_keys=True))
    return int(bool(verified["failures"]))


if __name__ == "__main__":
    sys.exit(main())
