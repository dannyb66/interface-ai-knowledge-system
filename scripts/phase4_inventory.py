#!/usr/bin/env python3
"""Inventory supplied source pages independently of the registry and extracted facts.

Run ``python scripts/phase4_inventory.py --snapshots snapshots``. Detailed output
defaults to ignored ``results/phase4/inventory``; only the aggregate census is
printed. Page IDs preserve raw variants, while canonical/content groups are hints
for a human source steward, NOT semantic claim clusters or evaluation partitions.

Traversal follows build_registry.py's manifest/block/row pattern. An empty
boilerplate filter keeps potential evidence; navigation/related-link labels are
review dispositions, never exclusions. Date cues are evidence to review, not
assertions that a date is applicable. No registry, runtime facts or evals are read.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.blocks import split_blocks, table_rows  # noqa: E402
from kb.normalize import canonical_url, parse_date  # noqa: E402
from kb.pagetype import classify  # noqa: E402

VERSION = "phase4-source-inventory-v1"
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LINK = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
RELATED = re.compile(r"\b(?:related (?:articles?|posts?|resources?)|you (?:may|might) also like|read next|"
                     r"handpicked for you|recommended (?:articles?|posts?))\b", re.I)
NAVIGATION = re.compile(r"^(?:navigation|menu|quick links|site map|follow us|connect with us)$", re.I)
DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
                  r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
                  r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
                  r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b", re.I)
DATE_CUE = re.compile(r"\b(effective|published|updated|expires?|through|until|as of)\b", re.I)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_digest(text: str) -> str:
    """Whitespace-only normalization; identical hashes do not prove equal meaning."""
    return digest(" ".join(text.split()).encode("utf-8"))


def date_evidence(lines: List[str]) -> List[dict]:
    evidence = []
    for number, line in enumerate(lines, 1):
        for match in DATE.finditer(line):
            raw = match.group(0)
            cue = list(DATE_CUE.finditer(line[:match.start()]))
            evidence.append({"line": number, "raw": raw, "parsed_date": parse_date(raw),
                             "preceding_cue": cue[-1].group(0).lower() if cue else None})
    return evidence


def disposition(headings: Tuple[str, ...], lines: Tuple[str, ...], kind: str) -> str:
    """Conservative labels to aid review; all labeled blocks remain in output."""
    if RELATED.search(" ".join(headings)) or any(RELATED.match(line) for line in lines[:1]):
        return "related_article_review"
    if any(NAVIGATION.fullmatch(heading) for heading in headings):
        return "navigation_review"
    if lines and all(LINK.search(line) and not re.sub(r"[\s*#|>•–—-]", "", LINK.sub("", line))
                     for line in lines):
        return "navigation_review"
    return "structure" if kind == "heading" else "content_review"


def block_records(page: dict, markdown: str, include_text: bool = False) -> List[dict]:
    lines, records, covered = markdown.splitlines(), [], set()
    dates = date_evidence(lines)

    def add(kind, idx, start, end, headings, body, effective=None, rows=None):
        record = {"page_id": page["page_id"], "snapshot_id": page["snapshot_id"],
                  "block_id": "{}:{}:{}".format(page["page_id"], kind, idx), "block_index": idx,
                  "kind": kind, "start_line": start, "end_line": end, "heading_path": list(headings),
                  "content_sha256": text_digest("\n".join(body)),
                  "disposition": disposition(headings, body, kind), "effective_date_cue": effective,
                  "date_evidence": [d for d in dates if start <= d["line"] <= end],
                  "row_count": len(rows or ()),
                  "column_kinds": sorted({c for row in rows or () for c in row.columns if c})}
        if include_text:
            record["text"] = "\n".join(body)
        records.append(record)

    # Public block parser, intentionally without the extraction boilerplate filter.
    for block in split_blocks(markdown, frozenset()):
        add(block.kind, block.idx, block.start_line, block.end_line, block.heading_path,
            block.lines, block.effective_date, table_rows(block) if block.kind == "table" else None)
        covered.update(range(block.start_line, block.end_line + 1))
    headings: List[Tuple[int, str]] = []
    for number, line in enumerate(lines, 1):
        match = HEADING.match(line.strip())
        if match:
            depth, title = len(match.group(1)), match.group(2)
            headings = [(level, name) for level, name in headings if level < depth] + [(depth, title)]
            add("heading", number, number, number, tuple(name for _, name in headings), (line.strip(),))
        elif line.strip() and number not in covered:
            add("unassigned", number, number, number, tuple(name for _, name in headings), (line.strip(),))
    return sorted(records, key=lambda r: (r["start_line"], r["end_line"], r["kind"], r["block_id"]))


def source_page(snapshot: Path, manifest: dict, index: int, raw: Any, seen: Counter) -> Tuple[dict, str]:
    errors, markdown, body = [], "", b""
    raw = raw if isinstance(raw, dict) else {}
    raw_file, url = raw.get("file"), raw.get("url")
    raw_file = raw_file if isinstance(raw_file, str) else ""
    url = url if isinstance(url, str) else ""
    cu = ""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("invalid URL")
        cu = canonical_url(url)
    except ValueError:
        errors.append("invalid_url")
    try:
        path = (snapshot / raw_file).resolve()
        path.relative_to(snapshot.resolve())
        if not raw_file or not path.is_file():
            raise ValueError("missing source file")
        body = path.read_bytes()
        markdown = body.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        errors.append("unreadable_or_unsafe_file")
    record_sha256 = digest(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    identity = json.dumps([snapshot.name, record_sha256, digest(body)], ensure_ascii=False)
    key = digest(identity.encode("utf-8"))
    occurrence = seen[key]
    seen[key] += 1
    page = {"page_id": "{}:{}".format(key, occurrence), "snapshot_id": snapshot.name,
            "manifest_snapshot_id": manifest.get("snapshot_id"), "manifest_index": index,
            "manifest_record_sha256": record_sha256,
            "manifest_path": "{}/manifest.json".format(snapshot.name), "raw_file": raw_file,
            "raw_url": url, "canonical_url": cu, "title": raw.get("title"),
            "taken_on": manifest.get("taken_on"), "fetched_at": raw.get("fetched_at"),
            "raw_sha256": digest(body), "content_sha256": text_digest(markdown),
            "page_type": classify(url, markdown) if cu else "unsupported",
            "line_count": len(markdown.splitlines()), "date_evidence": date_evidence(markdown.splitlines()),
            "errors": errors, "disposition": "quarantined" if errors else "source_review"}
    return page, markdown


def group_sources(pages: List[dict], blocks: List[dict]) -> dict:
    groups = {"canonical": defaultdict(list), "identical_content": defaultdict(list)}
    for page in pages:
        if page["canonical_url"]:
            groups["canonical"][page["canonical_url"]].append(page["page_id"])
        if not page["errors"] and page["line_count"]:
            groups["identical_content"][page["content_sha256"]].append(page["page_id"])
    repeated = defaultdict(list)
    for block in blocks:
        if block["kind"] not in ("heading", "unassigned"):
            repeated[block["content_sha256"]].append(block["block_id"])
    return {"schema_version": VERSION,
            "warning": "Source groups are review hints, not semantic claim clusters or independent samples.",
            "canonical_groups": [{"canonical_url": key, "page_ids": sorted(ids)}
                                 for key, ids in sorted(groups["canonical"].items())],
            "identical_content_groups": [{"content_sha256": key, "page_ids": sorted(ids)}
                                         for key, ids in sorted(groups["identical_content"].items()) if len(ids) > 1],
            "repeated_blocks": [{"content_sha256": key, "block_ids": sorted(ids)}
                                for key, ids in sorted(repeated.items()) if len(ids) > 1]}


def inventory(snapshots_dir: Path, include_text: bool = False) -> dict:
    manifests = sorted(snapshots_dir.glob("*/manifest.json"))
    if not manifests:
        raise ValueError("no snapshot manifests found")
    pages, blocks, snapshots = [], [], []
    for path in manifests:
        raw_manifest = path.read_bytes()
        manifest = json.loads(raw_manifest)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
            raise ValueError("invalid pages manifest: {}".format(path))
        seen, local = Counter(), []
        for index, raw in enumerate(manifest["pages"]):
            page, markdown = source_page(path.parent, manifest, index, raw, seen)
            local.append(page)
            blocks.extend(block_records(page, markdown, include_text))
        pages.extend(local)
        canonical = defaultdict(list)
        for page in local:
            if page["canonical_url"]:
                canonical[page["canonical_url"]].append(page)
        snapshots.append({"snapshot_id": path.parent.name, "manifest_sha256": digest(raw_manifest),
                          "pages": len(local), "canonical_urls": len(canonical),
                          "canonical_collision_groups": sum(len(group) > 1 for group in canonical.values()),
                          "distinct_content_collision_groups": sum(len({p["content_sha256"] for p in group}) > 1
                                                                   for group in canonical.values()),
                          "page_types": dict(sorted(Counter(p["page_type"] for p in local).items())),
                          "quarantined_pages": sum(bool(p["errors"]) for p in local)})
    pages.sort(key=lambda p: (p["snapshot_id"], p["page_id"]))
    blocks.sort(key=lambda b: (b["snapshot_id"], b["page_id"], b["start_line"], b["block_id"]))
    summary = {"schema_version": VERSION, "snapshots": snapshots, "pages": len(pages), "blocks": len(blocks),
               "quarantined_pages": sum(bool(p["errors"]) for p in pages),
               "block_dispositions": dict(sorted(Counter(b["disposition"] for b in blocks).items()))}
    return {"summary": summary, "pages": pages, "blocks": blocks, "source_clusters": group_sources(pages, blocks)}


def write_inventory(data: dict, out: Path) -> None:
    """Protect the checkout from accidentally tracking private source metadata/text."""
    resolved = out.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        relative = None
    if relative is not None and relative.parts[:2] != ("results", "phase4"):
        raise ValueError("inside this checkout, detailed inventory must use ignored results/phase4/")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("pages", "blocks"):
        with (out / (name + ".jsonl")).open("w", encoding="utf-8") as stream:
            for row in data[name]:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    for name in ("summary", "source_clusters"):
        (out / (name + ".json")).write_text(json.dumps(data[name], ensure_ascii=False, sort_keys=True, indent=2)
                                            + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshots", type=Path, default=ROOT / "snapshots")
    parser.add_argument("--out", type=Path, default=ROOT / "results/phase4/inventory")
    parser.add_argument("--include-text", action="store_true", help="include private block text in local output")
    args = parser.parse_args(argv)
    try:
        data = inventory(args.snapshots, args.include_text)
        write_inventory(data, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(data["summary"], sort_keys=True))
    return int(bool(data["summary"]["quarantined_pages"]))


if __name__ == "__main__":
    sys.exit(main())
