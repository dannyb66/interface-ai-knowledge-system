"""Verify all curated source variants and v2 pins. No evaluation files are read."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.prose_facts import load_prose
from kb.extract_fees import EFFECTIVE, clean
from kb.normalize import parse_date
from kb.registry import Registry
from kb.source_pages import normalized
from kb.temporal import published_date
from kb.verify import quote_found
from phase4_sources import source_crawls


def verify_entries(entries, pages):
    """Require complete quote-bearing canonical sets and every declared exact pin.

    Legacy totals count canonical page/crawl pairs. V2 pins additionally account
    for raw aliases and content collisions; a valid alternate cannot hide a bad
    pin. For dated v2 claims the omitted-source census is scoped to the same
    actual publication date. Independent source review must establish that those
    pages also share subject/predicate context; a date alone is not proof. The
    legacy census remains unchanged. No diagnostics reproduce source extracts.
    """
    verified = total = 0
    failures, cache = [], {}
    verified_pins = total_pins = 0
    for i, entry in enumerate(entries):
        for sid in entry.crawls:
            crawl = pages.get(sid)
            found = [p for rows in (crawl.groups.values() if crawl else ()) for p in rows
                     if quote_found(entry.quote, normalized(p, cache))]
            if entry.semantics is not None and entry.published_date:
                found = [p for p in found if published_date(p.markdown) == entry.published_date]
            matching = {p.canonical_url for p in found}
            listed = set(entry.canonical_urls)
            verified += len(matching & listed)
            total += len(listed)
            if matching != listed:
                failures.append("entry {} {} @{} missing={} omitted={}".format(i, entry.product_id, sid,
                    sorted(listed - matching), sorted(matching - listed)))
            actual = {(p.raw_url, p.content_sha256) for p in found}
            expected = {(p.raw_url, p.content_sha256) for p in entry.source_pins if p.snapshot_id == sid}
            if entry.source_pins:
                total_pins += len(expected)
                verified_pins += len(actual & expected)
                if expected != actual:
                    failures.append("entry {} {} @{} source pins missing={} omitted={}".format(
                        i, entry.product_id, sid, sorted(expected - actual), sorted(actual - expected)))
            elif crawl and any(crawl.ambiguous(p) for p in found):
                failures.append("entry {} {} @{} unpinned ambiguous raw source".format(i, entry.product_id, sid))
            for page in found:
                if page.canonical_url in listed and entry.published_date and published_date(page.markdown) != entry.published_date:
                    failures.append("entry {} {} @{} publication date differs on {}".format(i, entry.product_id, sid, page.raw_url))
                if page.canonical_url in listed and entry.semantics is not None and entry.attribute == "fee":
                    dates = {parse_date(m.group(1)) for m in EFFECTIVE.finditer(clean(page.markdown))}
                    if dates and dates != {entry.effective_date} or entry.effective_date and not dates:
                        failures.append("entry {} {} @{} fee effective date absent or differs on {}".format(
                            i, entry.product_id, sid, page.raw_url))
    return {"verified": verified, "total": total, "verified_pins": verified_pins,
            "total_pins": total_pins, "failures": failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    parser.add_argument("--catalog", type=Path, default=ROOT / "submission/data/prose_facts.json")
    parser.add_argument("--products", type=Path, default=ROOT / "submission/data/products.json")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    entries = load_prose(args.catalog, Registry.load(args.products))
    report = verify_entries(entries, source_crawls(args.snapshots))
    print("prose: {verified}/{total} verified (entry x page x crawl); pins: {verified_pins}/{total_pins}".format(**report))
    for failure in report["failures"]:
        print(failure, file=sys.stderr)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int(bool(report["failures"]))


if __name__ == "__main__":
    sys.exit(main())
