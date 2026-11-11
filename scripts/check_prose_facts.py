"""Verify every curated triple and find omitted source pages. No evaluation questions are read."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.prose_facts import load_prose
from kb.registry import Registry
from kb.temporal import published_date
from kb.verify import quote_found
from curate_prose_catalog import all_pages


def main():
    pages = all_pages()
    raw_pages = all_pages(normalized=False)
    entries = load_prose(ROOT / "submission/data/prose_facts.json", Registry.load())
    verified = total = 0
    failures = []
    for i, entry in enumerate(entries):
        for sid in entry.crawls:
            matching = {url for url, text in pages.get(sid, {}).items() if quote_found(entry.quote, text)}
            listed = set(entry.canonical_urls)
            verified += len(matching & listed)
            total += len(listed)
            if matching != listed:
                failures.append("entry {} {} @{} missing={} omitted={}".format(i, entry.product_id, sid,
                    sorted(listed - matching), sorted(matching - listed)))
            for url in sorted(listed & matching):
                if entry.published_date and published_date(raw_pages[sid][url]) != entry.published_date:
                    failures.append("entry {} {} @{} publication date differs on {}".format(i, entry.product_id, sid, url))
    print("prose: {}/{} verified (entry x page x crawl)".format(verified, total))
    for failure in failures:
        print(failure, file=sys.stderr)
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
