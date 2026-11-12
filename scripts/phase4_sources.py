"""Offline source loading shared by reviewed-candidate tools; no eval files are read."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.source_pages import SourcePage, SourcePages, source_page


@dataclass(frozen=True)
class SourceRecord:
    page: SourcePage
    relative_file: str
    manifest_index: int


def source_records(root: Path) -> Tuple[SourceRecord, ...]:
    """Preserve manifest records and raw aliases; never overwrite canonical URLs."""
    records = []
    for directory in sorted(Path(root).iterdir()):
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            continue
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        sid = meta["snapshot_id"]
        if not isinstance(sid, str) or not sid:
            raise ValueError("invalid snapshot identity")
        for index, raw in enumerate(meta["pages"]):
            path = (directory / raw["file"]).resolve()
            path.relative_to(directory.resolve())
            markdown = path.read_bytes().decode("utf-8")
            page = source_page(sid, raw["url"], markdown, raw.get("title") or "",
                               raw.get("fetched_at") or "")
            records.append(SourceRecord(page, str(path.relative_to(Path(root).resolve())), index))
    if not records:
        raise ValueError("no source pages found")
    return tuple(records)


def source_crawls(root: Path) -> Dict[str, SourcePages]:
    grouped = {}
    for record in source_records(root):
        grouped.setdefault(record.page.snapshot_id, []).append(record.page)
    return {sid: SourcePages(pages) for sid, pages in sorted(grouped.items())}
