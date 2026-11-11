"""Ask the system one question and show what it did.

    python scripts/ask.py "<question>" [--as-of D] [--explain]

Prints the answer text, the ``confident`` flag and the sources. With ``--explain`` it then prints the dict
that ``KnowledgeSystem.explain()`` returns as indented JSON, whatever keys that facade provides (the script
assumes none of them). A malformed ``--as-of`` or an empty or over-long question also prints its ``KB-E04``
or ``KB-E05`` registry line on stderr; the answer is still shown, so you see what the system did with it.
Snapshots come from ``snapshots/`` and whatever ingestion prints goes to stderr, which keeps stdout for the
answer. The repo root comes from this file's location, so any working directory works. Runs on Python 3.9
and newer.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission"):
    sys.path.insert(0, str(ROOT / _folder))

import solution  # noqa: E402
from kb.errors import warn_once  # noqa: E402
from kb.normalize import parse_as_of  # noqa: E402
from run_eval import load_snapshots, to_answer  # noqa: E402

DEFAULT_LIMIT = 1000


def build_system():
    """The facade with every snapshot ingested; anything ingestion prints goes to stderr."""
    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    return ks


def warn_on_input(question: str, as_of: Optional[str], limit: int) -> None:
    """Print the registry line for an input the system refuses (it takes whatever ``parse_as_of`` takes)."""
    if as_of is not None and parse_as_of(as_of) is None:
        warn_once("KB-E04", value=as_of)
    if not question.strip() or len(question) > limit:
        warn_once("KB-E05", limit=limit)


def show_answer(answer) -> None:
    print("answer: %s" % answer.text)
    print("confident: %s" % answer.confident)
    if answer.conflict_note:
        print("conflict_note: %s" % answer.conflict_note)
    if not answer.sources:
        print("sources: none")
        return
    print("sources:")
    for source in answer.sources:
        snapshot = " [%s]" % source.snapshot_id if source.snapshot_id else ""
        print("  - %s%s" % (source.url, snapshot))
        if source.quote:
            print("      quote: %s" % source.quote)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the knowledge system one question.")
    parser.add_argument("question", help="the member question, quoted")
    parser.add_argument("--as-of", dest="as_of", metavar="D", default=None,
                        help="answer as the site stood on this date (YYYY-MM-DD)")
    parser.add_argument("--explain", action="store_true", help="also print explain() as indented JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ks = build_system()
    limit = getattr(getattr(ks, "config", None), "max_question_chars", DEFAULT_LIMIT)
    warn_on_input(args.question, args.as_of, limit if isinstance(limit, int) else DEFAULT_LIMIT)
    show_answer(to_answer(ks.answer(args.question, args.as_of)))
    if args.explain:
        try:
            info = ks.explain(args.question, args.as_of)
        except Exception as exc:  # a broken explain() is the thing being debugged: say so, exit non-zero
            print("kb: explain() raised %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
            return 1
        print("explain:")
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
