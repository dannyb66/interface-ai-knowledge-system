"""A deterministic corpus of probe questions and their canonical keys, the base for parse-change diffs.

    python scripts/build_probe_corpus.py --out PATH [--limit N] [--questions-from OLD]

Writes ``{"version": 1, "count": n, "keys": {question: canonical_key}}`` with sorted keys. The questions are frames
filled from the registry's names and aliases and the ``SYNONYMS`` phrases (``lexicon.PRODUCT_KINDS`` as products,
``attribute`` phrases as attributes), and from fixed term, amount, model-year, date, day, branch and count phrasings,
in separate blocks whose sizes add up (132,192 questions on the Phase 2 gate code). The questions are deduplicated
and sorted, and ``--limit`` (at least 1) samples N evenly across that order while retaining fixed probes. This
keeps new registry vocabulary from starving the tail's intents. ``--questions-from OLD`` adds every
question of the corpus OLD, so a phrase this tree no longer generates (a removed or renamed synonym or alias) is
still parsed and shows in the diff as a changed key. Only these questions are parsed, through
``KnowledgeSystem._parse`` (the graded path's parse, ``reference_date`` from the newest crawl) with ``as_of`` ``None``.

Every input is read in a sorted order, so the file is byte-identical under any ``PYTHONHASHSEED``. A task that adds
names or synonyms adds questions, which the diff counts but does not compare. The repo root comes from this file's
location; snapshots come from ``snapshots/`` and ingestion's stdout goes to stderr. A task's parse check:

    python scripts/build_probe_corpus.py --out results/p3/probe_<task>.json --questions-from results/p3/probe_base.json
    python scripts/diff_probe_keys.py results/p3/probe_base.json results/p3/probe_<task>.json
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
for _folder in ("harness", "submission", "scripts"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

from diff_probe_keys import load as load_corpus  # noqa: E402  (the one reader of the corpus format)

VERSION = 1

# product phrase x attribute phrase
ATTRIBUTE_FRAMES = ("What is the {a} on the {p}?", "What's the {p} {a}?", "Does the {p} have a {a}?")
# product phrase alone: every intent the parser knows that a product can carry
PRODUCT_FRAMES = (
    "What is the {p} rate?", "What are the {p} rates?", "What rates do you offer on {p}?",
    "Which {p} options do you offer?", "How do I open a {p}?", "How can I apply for a {p}?",
    "Where can I find the {p} page on the website?", "What is the URL for the {p}?", "Is the {p} still available?",
    "Do you offer a {p}?", "What was the previous {p} rate?", "What did the {p} pay before it changed?",
    "What is the highest {p} rate?", "What is the lowest {p} APR?", "What is the best {p} rate?",
    "What is the minimum to open a {p}?", "How much do I need to open a {p}?", "What are the fees on the {p}?",
    "Who is eligible for the {p}?", "Tell me about the benefits of the {p}.",
)
TERMS = ("3-month", "6 month", "7-month", "10-month", "12-month", "13 month", "17-month", "18 months", "24-month",
         "36-month", "48-month", "60-month", "72 month", "84-month", "1-year", "5-year", "10-year", "15-year",
         "30-year fixed", "7/1 ARM", "5/5 ARM", "one-year", "seventeen-month", "two year")
TERM_FRAMES = ("What is the APY on the {t} {p}?", "What rate does a {t} {p} pay?")
AMOUNTS = ("$5", "$100", "$500", "$1,000", "$2,500", "$10,000", "$24,999.99", "$25,000", "$50,000", "$100,000",
           "$250,000", "$1,000,000", "25k", "$25k", "25,000 dollars", "$500.00")
AMOUNT_FRAMES = ("What is the rate on the {p} for {m}?", "Do I need {m} to open a {p}?")
MODEL_YEARS = ("2012", "2016", "2018", "2020", "2022", "2024", "2025", "2026")
MODEL_YEAR_FRAMES = ("What is the APR on a {y} {p}?", "What rate can I get on a {y} model year {p}?")
DATES = ("as of May 2026", "as of 2026-05", "in October 2026", "on May 31, 2026", "on 05/31/2026", "on 2026-06-01",
         "at the end of June 2026", "in mid-August 2026", "in early September 2026", "in May", "last year", "in 2024",
         "on January 15, 2026", "as of April 30, 2026")
DATE_FRAMES = ("What was the {p} rate {d}?", "What was the APY on the {p} {d}?")
DATE_PAIRS = (("May 2026", "September 2026"), ("May 12", "September 28, 2026"), ("May 13", "May 18, 2026"),
              ("September", "May 2026"), ("June 1, 2026", "August 31, 2026"), ("2025", "2026"),
              ("the May 12 crawl", "the September 28 crawl"))
CHANGE_FRAMES = ("How did the {p} rate change between {a} and {b}?", "Did the {p} APY change from {a} to {b}?")
SINCE = ("May 2026", "June 2026", "last year", "2025", "May 19, 2026")
SINCE_FRAMES = ("Has the {p} rate changed since {d}?",)
COORDINATION_FRAMES = ("What are the rates on {p} and {q}?",)
BRANCHES = ("Mullan Avenue", "Hy-Vee", "Asbury", "Asbury Road", "Dubuque", "Flint Hill Drive", "Hillcrest Road",
            "Oldenburg Lane", "Pennsylvania Avenue", "Peosta Street", "Sycamore Street", "Cedar Rapids", "Waterloo",
            "Dyersville", "Galena", "Platteville", "Manchester", "Maquoketa", "Iowa City", "Mars")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Saturdays", "weekends",
        "Saturday and Sunday")
BRANCH_DAY_FRAMES = ("What are the {b} branch hours on {d}?", "Is the {b} branch open on {d}?",
                     "What time does the {b} office close on {d}?", "When does the {b} location open on {d}?",
                     "What are the drive-up hours at the {b} branch on {d}?")
BRANCH_FRAMES = ("What is the phone number of the {b} branch?", "What is the address of the {b} branch?",
                 "Where is the {b} branch located?", "Is the {b} branch still open?", "When did the {b} branch close?",
                 "Is the {b} branch closing?", "What is the lobby phone number for {b}?",
                 "What are the hours for the {b} branch?")
DAY_FRAMES = ("What are your hours on {d}?", "Are you open on {d}?", "What are the lobby hours on {d}?",
              "What are the drive-up hours on {d}?")
COUNT_NOUNS = ("branches", "branch offices", "branch locations", "locations", "employees", "members", "counties",
               "volunteer hours", "ATMs", "VTO users")
COUNT_YEARS = ("", " in 2019", " in 2020", " in 2021", " in 2022", " in 2023", " in 2024", " in 2025", " in 2026",
               " last year", " this year", " as of August 2024")
COUNT_FRAMES = ("How many {n} does Dupaco have{y}?", "How many {n} did Dupaco have{y}?",
                "What was the number of {n}{y}?")
ASSET_FRAMES = ("What were Dupaco's total assets{y}?",)
FIXED = ("What is Dupaco's routing number?", "What is the ABA number?", "Can you repeat the routing number?",
         "What is Dupaco's phone number?", "What is the fax number?", "What is the email address?",
         "How long does Dupaco take to reply to messages?", "What is the address of Dupaco's main office?",
         "Where can I find a branch or ATM near me?", "What is Dupaco's website?", "How do I contact Dupaco?",
         "What is the toll-free number?", "When do you reply to emails?", "What are your call center hours?",
         "What are the hours?", "What are the rates?", "What are all your loan rates?",
         "What savings accounts do you offer?")


def _fill(frames: Sequence[str], **slots: Sequence[str]) -> Iterable[str]:
    """Every frame with every combination of the named slot phrasings."""
    names = sorted(slots)
    combos: List[dict] = [{}]
    for name in names:
        combos = [dict(c, **{name: value}) for c in combos for value in slots[name]]
    for frame in frames:
        for combo in combos:
            yield frame.format(**combo)


def phrases(registry: Any) -> tuple:
    """(product phrases, attribute phrases), each sorted and unique: the registry's display names and aliases plus
    the ``SYNONYMS`` phrases that name a product, and the ``SYNONYMS`` attribute phrases."""
    from kb.lexicon import PRODUCT_KINDS, SYNONYMS

    aliases = registry.aliases()
    products: Set[str] = set(aliases)
    products |= {registry.display_name(pid) for pid in sorted(set(aliases.values()))}
    products |= {phrase for phrase, (kind, _) in SYNONYMS.items() if kind in PRODUCT_KINDS}
    attributes = {phrase for phrase, (kind, _) in SYNONYMS.items() if kind == "attribute"}
    return sorted(products), sorted(attributes)


def questions(registry: Any) -> List[str]:
    """Every probe question, deduplicated and sorted."""
    products, attributes = phrases(registry)
    names = sorted({registry.display_name(pid) for pid in set(registry.aliases().values())})
    out: Set[str] = set(FIXED)
    out.update(_fill(ATTRIBUTE_FRAMES, p=products, a=attributes))
    out.update(_fill(PRODUCT_FRAMES, p=products))
    out.update(_fill(TERM_FRAMES, p=products, t=TERMS))
    out.update(_fill(AMOUNT_FRAMES, p=products, m=AMOUNTS))
    out.update(_fill(MODEL_YEAR_FRAMES, p=products, y=MODEL_YEARS))
    out.update(_fill(DATE_FRAMES, p=products, d=DATES))
    for a, b in DATE_PAIRS:
        out.update(_fill(CHANGE_FRAMES, p=products, a=(a,), b=(b,)))
    out.update(_fill(SINCE_FRAMES, p=products, d=SINCE))
    out.update(frame.format(p=p, q=q) for frame in COORDINATION_FRAMES for p in names for q in names if p != q)
    out.update(_fill(BRANCH_DAY_FRAMES, b=BRANCHES, d=DAYS))
    out.update(_fill(BRANCH_FRAMES, b=BRANCHES))
    out.update(_fill(DAY_FRAMES, d=DAYS))
    out.update(_fill(COUNT_FRAMES, n=COUNT_NOUNS, y=COUNT_YEARS))
    out.update(_fill(ASSET_FRAMES, y=COUNT_YEARS))
    return sorted(out)


def build_system():
    """``solution.build()`` with every crawl under ``snapshots/`` ingested; ingestion's stdout goes to stderr."""
    import solution
    from run_eval import load_snapshots

    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    return ks


def corpus(ks: Any, limit: Optional[int] = None, extra: Iterable[str] = ()) -> dict:
    """The corpus of ``limit`` generated questions (all when ``None``) in sorted order plus the questions
    in ``extra`` (``--questions-from``), as written to ``--out``."""
    every = questions(ks.registry)
    if limit is None or limit >= len(every):
        kept = every
    else:
        fixed = sorted(set(FIXED))[:limit]
        remaining = sorted(set(every) - set(fixed))
        n = limit - len(fixed)
        kept = sorted(fixed + [remaining[i * len(remaining) // n] for i in range(n)])
    asked = sorted(set(kept).union(extra))
    print("probe corpus: {} questions generated, {} kept, {} parsed".format(len(every), len(kept), len(asked)),
          file=sys.stderr)
    keys = {q: ks._parse(q, None).canonical_key for q in asked}
    return {"version": VERSION, "count": len(keys), "keys": keys}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the probe corpus: question -> canonical key.")
    parser.add_argument("--out", metavar="PATH", required=True, help="where to write the corpus JSON")
    parser.add_argument("--limit", metavar="N", type=int, default=None, help="sample N questions across all generated wording")
    parser.add_argument("--questions-from", metavar="OLD", default=None,
                        help="also parse every question of this corpus, so a removed phrase shows as a changed key")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    extra = sorted(load_corpus(args.questions_from)) if args.questions_from else []
    data = corpus(build_system(), args.limit, extra)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
