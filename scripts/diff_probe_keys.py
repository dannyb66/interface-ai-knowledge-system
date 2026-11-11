"""Compare two probe corpora (``scripts/build_probe_corpus.py``) question by question.

    python scripts/diff_probe_keys.py OLD NEW

Prints ``changed <n> of <m>``, where ``m`` counts the questions both corpora hold, then one line per change class
with its count and up to 5 examples (``question: old key -> new key``, first in sorted question order). The classes
are the fields of ``Query.canonical_key`` (``intent|product|attribute|slots|as_of``, then ``|past`` when the question
asks for a past value): ``intent``, ``product``, ``attribute``, ``slots``, ``as_of`` and ``past``. A changed key
counts in every class whose field differs. Questions only one corpus holds are not compared, and their numbers close
the report. Questions only in NEW are added names or synonyms. Questions only in OLD are phrases the new tree no
longer generates, whose parse would go unseen: up to 5 are shown and the exit status is 1, until NEW is rebuilt with
``build_probe_corpus.py --questions-from OLD``, which parses them too.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, NoReturn, Optional

CLASSES = ("intent", "product", "attribute", "slots", "as_of", "past")
EXAMPLES = 5
_PAST = "|past"


def key_fields(key: str) -> Dict[str, str]:
    """The canonical key's fields by class; a key of another shape still splits, never raises."""
    past = key.endswith(_PAST)
    body = key[:-len(_PAST)] if past else key
    intent, product, attribute, rest = (body.split("|", 3) + ["", "", ""])[:4]
    slots, _, as_of = rest.rpartition("|")
    return {"intent": intent, "product": product, "attribute": attribute, "slots": slots, "as_of": as_of,
            "past": str(past)}


def _fail(message: str) -> NoReturn:
    """One line on stderr, then exit status 2, as for a usage error."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


def load(path: str) -> Dict[str, str]:
    """The ``keys`` of the version 1 probe corpus at ``path``. A missing or unreadable file, one that is not JSON or
    not such a corpus is one line on stderr and exit status 2 (``results/p3/`` is git-ignored: a fresh checkout has
    no ``probe_base.json`` until it is built)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        _fail("cannot read probe corpus {}: {}; build one with scripts/build_probe_corpus.py --out {}".format(
            path, exc.strerror or exc, path))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        _fail("probe corpus {} is not JSON: {}".format(path, exc))
    keys = data.get("keys") if isinstance(data, dict) and data.get("version") == 1 else None
    if not isinstance(keys, dict) or not all(isinstance(key, str) for key in keys.values()):
        _fail("{} is not a version 1 probe corpus".format(path))
    return keys


def report(old: Dict[str, str], new: Dict[str, str]) -> List[str]:
    """The report's lines (see the module docstring)."""
    shared = sorted(set(old) & set(new))
    changed = [q for q in shared if old[q] != new[q]]
    lines = ["changed {} of {}".format(len(changed), len(shared))]
    for name in CLASSES:
        hits = [q for q in changed if key_fields(old[q])[name] != key_fields(new[q])[name]]
        lines.append("{} {}".format(name, len(hits)))
        lines.extend("  {!r}: {} -> {}".format(q, old[q], new[q]) for q in hits[:EXAMPLES])
    only_old, only_new = sorted(set(old) - set(new)), len(set(new) - set(old))
    if only_old or only_new:
        lines.append("not compared: {} only in OLD, {} only in NEW".format(len(only_old), only_new))
    if only_old:
        lines.append("only in OLD (rebuild NEW with --questions-from OLD to compare them):")
        lines.extend("  {!r}".format(q) for q in only_old[:EXAMPLES])
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    """Print the report; exit status 1 when OLD holds questions NEW does not, else 0."""
    parser = argparse.ArgumentParser(description="Compare two probe corpora by canonical key.")
    parser.add_argument("old", help="the reference corpus, e.g. results/p3/probe_base.json")
    parser.add_argument("new", help="the corpus to compare with it")
    args = parser.parse_args(argv)
    old, new = load(args.old), load(args.new)
    print("\n".join(report(old, new)))
    return 1 if set(old) - set(new) else 0


if __name__ == "__main__":
    sys.exit(main())
