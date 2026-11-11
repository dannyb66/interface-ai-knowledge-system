"""The parsed ``Query`` of every public and dev eval item, and optionally each item's answer.

    python scripts/dump_eval_keys.py [--out PATH] [--answers PATH]

Each item of ``eval/public_eval.jsonl`` and ``eval/dev_extra.jsonl`` (read by name: nothing else under ``eval/``)
goes through ``KnowledgeSystem._parse``, the graded path's parse: the question cut to ``max_question_chars`` and the
newest crawl's day as ``reference_date``. It is parsed twice, with the item's ``as_of`` (key ``<id>|item``) and with
``None`` (key ``<id>|none``): 120 keys for the 60 items. ``query_dict`` writes a ``Query`` as JSON: tuples as lists,
``question_numbers`` sorted, and a field equal to its dataclass default left out, so a field added later leaves the
fixture alone until a question sets it.

``--out`` writes the keys there; ``tests/fixtures/eval_keys.json`` is the 60-key fixture, and every difference from
it is listed in ``tests/fixtures/eval_key_changes.json`` with its task and reason (``tests/test_26_eval_keys.py``).
``--answers`` writes each item's ``render_with_dropped`` answer for the item's own ``as_of``: its text, confident
flag, conflict note, sources and the sentences the lint dropped, plus ``facade_same``, whether ``ks.answer()``
returns that same answer, on a first call and on a repeat; the exit status is 1, with the items named on stderr,
when any does not. With neither flag the keys go to stdout; with ``--answers`` alone no keys are written, so the
fixture is only ever rewritten by an explicit ``--out``.

Snapshots come from ``snapshots/`` and whatever ingestion prints goes to stderr. Both files hold one sorted key per
line, so two runs on the same code are byte-identical and a changed item is one changed line. The repo root comes
from this file's location, so any working directory works.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

EVAL_FILES = ("public_eval.jsonl", "dev_extra.jsonl")


def load_items() -> List[dict]:
    """The public items, then the dev items, in file order."""
    items = []
    for name in EVAL_FILES:
        for line in (ROOT / "eval" / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
    return items


def build_system():
    """``solution.build()`` with every crawl under ``snapshots/`` ingested; ingestion's stdout goes to stderr."""
    import solution
    from run_eval import load_snapshots

    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    return ks


def _plain(value: Any) -> Any:
    """``value`` in JSON shapes: tuples as lists, sets as lists sorted by their JSON text."""
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def query_dict(q: Any) -> dict:
    """The fields of ``q`` as JSON, as the fixture file holds them: tuples as lists, ``question_numbers`` sorted by
    (unit, value), and every field equal to its dataclass default omitted."""
    out: Dict[str, Any] = {}
    for field in dataclasses.fields(q):
        value = getattr(q, field.name)
        if field.default is not dataclasses.MISSING and value == field.default:
            continue
        if field.default_factory is not dataclasses.MISSING and value == field.default_factory():
            continue
        if field.name == "question_numbers":
            value = [list(t) for t in sorted(value, key=lambda t: (str(t[0]), float(t[1])))]
        out[field.name] = _plain(value)
    return json.loads(json.dumps(out))


def current_keys(ks: Any) -> Dict[str, dict]:
    """``query_dict`` of every item parsed with its own ``as_of`` (``<id>|item``) and with ``None`` (``<id>|none``)."""
    keys: Dict[str, dict] = {}
    for item in load_items():
        keys[item["id"] + "|item"] = query_dict(ks._parse(item["question"], item.get("as_of")))
        keys[item["id"] + "|none"] = query_dict(ks._parse(item["question"], None))
    return keys


def _answer_dict(answer: Any) -> dict:
    return {"text": answer.text, "confident": answer.confident, "conflict_note": answer.conflict_note,
            "sources": [{"url": s.url, "snapshot_id": s.snapshot_id, "quote": s.quote} for s in answer.sources or ()]}


def current_answers(ks: Any) -> Dict[str, dict]:
    """Each item's ``render_with_dropped`` answer for its own ``as_of``, keyed by item id, with the dropped sentences
    and ``facade_same``: whether ``ks.answer()``, the graded facade with its cache, returns that same answer (text,
    confident flag, conflict note and sources) and then the same again when asked twice (the cache-hit path the
    harness's repeat checks take), so a lint or cache regression cannot hide."""
    from kb.compose import render_with_dropped
    from kb.conflicts import with_note
    from kb.resolve import resolve

    out: Dict[str, dict] = {}
    for item in load_items():
        question, as_of = item["question"], item.get("as_of")
        plan = resolve(ks._parse(question, as_of), ks.store, ks.registry)
        answer, dropped = render_with_dropped(plan)
        notes = getattr(ks, "_notes", None)  # the facade's curated-conflict note step (absent on a bare test double)
        shown = _answer_dict(with_note(answer, plan, notes) if notes is not None else answer)
        first = _answer_dict(ks.answer(question, as_of))
        repeat = _answer_dict(ks.answer(question, as_of))  # served from the answer cache
        out[item["id"]] = dict(shown, dropped=list(dropped), facade_same=first == shown and repeat == first)
    return out


def dumps(data: Dict[str, Any]) -> str:
    """The one serialiser of both files: one key per line in sorted order, its value as compact JSON with sorted
    keys (the fixture is 122 lines, under the 500-line rule for ``tests/``), UTF-8 text kept, a trailing newline."""
    rows = ["{}: {}".format(json.dumps(k, ensure_ascii=False), json.dumps(v, sort_keys=True, ensure_ascii=False))
            for k, v in sorted(data.items(), key=lambda item: item[0])]
    return "{\n" + ",\n".join(rows) + "\n}\n"


def _write(path: str, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(data), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dump the eval items' parse keys and, optionally, their answers.")
    parser.add_argument("--out", metavar="PATH", help="write the 120 parse keys here")
    parser.add_argument("--answers", metavar="PATH", help="write each item's answer here")
    args = parser.parse_args(argv)
    ks = build_system()
    if args.out or not args.answers:
        keys = current_keys(ks)
        if args.out:
            _write(args.out, keys)
        else:
            sys.stdout.write(dumps(keys))
    if args.answers:
        answers = current_answers(ks)
        _write(args.answers, answers)
        diverged = sorted(item for item, answer in answers.items() if not answer["facade_same"])
        if diverged:
            print("dump_eval_keys: ks.answer() differs from render_with_dropped for {} items: {}".format(
                len(diverged), ", ".join(diverged)), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
