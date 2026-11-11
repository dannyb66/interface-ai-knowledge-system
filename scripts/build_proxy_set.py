#!/usr/bin/env python3
"""The proxy and holdout eval sets, generated from this system's own fact store (plan A Task 20).

    python scripts/build_proxy_set.py --split proxy|holdout [--templates PATH] [--out PATH]

1. Ingests every crawl under snapshots/ (``solution.build()``; ingestion output goes to stderr).
2. Splits fact keys by ``sha1(repr(key))``: a last hex digit below ``d`` is the proxy's, any other the holdout's. Only
   the (product_id, attribute) pairs a family lists in the frozen eval/proxy/universe.json are sampled.
3. Fills the split's templates per family (format below). 4. ``must_include`` holds the value in force and
   ``must_not_include`` the same key's other crawl values (rates), its other publications (dated facts) or, for a key
   with a ``year``, the product's other years. Tier questions also trap sibling tiers; hours questions trap other
   branches' schedules, excluding tokens contained in the correct schedule.
5. One ``group`` per fact and asked variant (date, endpoints, amount), so a family's templates form paraphrase groups.
   Items also carry ``family``, ``template``, ``route`` ([intent, product_id, attribute]: the parse the template
   means, which scripts/proxy_routing.py checks) and ``key`` (the split key's repr); the harness ignores them.
6. The proxy split adds the seeds (eval/proxy/seeds/): a paraphrase is its public original with the new question
   (tokens, category, weight, sources and group kept) and ``origin`` naming it; a probe becomes an item. The holdout
   adds none.
7. Drops near-duplicates of a public or dev question (equal ``norm_text`` or word tokens, or a token Jaccard above
   0.8), for the holdout also of a proxy question, and template items whose (question, as_of) another item asks with
   other tokens (a seed wins; two template items both go).
8. Orders items by family, template id and key string and writes JSON lines to --out (default
   eval/proxy/<split>.jsonl); the same snapshots give byte-identical output under any PYTHONHASHSEED.

Value in force: in the crawl a date falls in, the key's best-ranked fact among the pair's facts in force that day
(``FactStore.in_force``), of the top authority class, table rows only when there are any. A (template, key, date) is
skipped when another such key fits every qualifier the question states and holds another value (an ambiguous
question measures the template, not the system). Dated families read the newest crawl, newest publication per key.
Dates asked: as_of, the first, middle or last day of the last crawl that held the value (by key hash, the first one
in force); change, a first or middle day of each crawl (its last day as a fallback). A day a later crawl's notice
already dates another value from (``Ctx.contested``: taken_i < effective date <= day) is never asked there; the crawl's
own day always can be. The ``contested_day`` kind asks exactly those days, in a family of weight 0.

--templates (the proxy's default is eval/proxy/proxy_templates.json; --split holdout must name its own, ids "h-...")::

  {"names": {"<product_id>": "<pattern>"},          # how {name} reads; may use the qualifier placeholders
   "name_sets": {"<set>": {"<product_id>": "<pattern>"}},   # optional other wordings a template can pick
   "attributes": {"<attribute>": "<phrase>"},       # how {attr} reads (default: the attribute, "_" as " ")
   "families": {"<family>": {
       "kind": "<kind>", "category": "<category>", "intent": "<parser intent>",
       "trap_category": "<category when must_not_include is non-empty>",   # optional
       "weight": <number>,                                  # optional, default 1; 0: reported, never gating, no groups
       "forbid": ["<qualifier>"], "require_any": ["<qualifier>"],          # optional key filters
       "names": {"<product_id>": "<pattern>"},                             # optional, beats the top-level names
       "templates": [{"id": "<unique id>", "text": "<question with placeholders>",
                      "as_of": "text" | "argument",       # as_of kind: {date} in the text, or the item's as_of
                      "endpoints": "consecutive" | "to_latest",   # change kind: neighbouring crawls, or to the newest
                      "attributes": ["<attribute>"],      # optional: only facts of these attributes
                      "name_set": "<set>",                # optional: its names beat the family's and the top level's
                      "attr_words": {"<attribute>": "<phrase>"}, "intent": "<parser intent>"}]}}}

Kinds (scripts/proxy_kinds.py): ``current`` (each key in force now), ``as_of`` (each older value of a key),
``contested_day`` (an older value on a contested day), ``change`` (changed and unchanged adjacent crawl spans), ``tier_amount`` (each
balance or loan-amount tier, asked with an amount inside it), ``unpublished`` (each pair with no fact now: must
refuse), ``dated`` (each dated fact: an hours line, a closure, a count) and ``dated_branch`` (one branch's dated facts
of one attribute), and ``unlisted_branch`` (refuse a named branch with no published schedule; ``branches`` supplies
the candidate names). Placeholders: {name} {attr}; the key's {term} ("17-month") {months} {years} ("30-year") {jumbo}
{special} {intro} {program} {model_year} {loan_amount} (" for loans of $X or less"); {amount} (tier_amount); {date}
(as_of, contested_day); {date_from} {date_to} (change); {branch} {day} {year} (dated kinds).
This plan's families (kind: category, intent, filters): rate_current current: current_value, value, forbid
balance_min and balance_max, trap_category stale_trap; rate_as_of as_of: temporal_as_of, value, same forbid;
rate_change change: change_between_snapshots, change, same forbid; tier_amount tier_amount: tier_disambiguation,
value, require_any balance_min, balance_max, loan_amount_max; refuse_unpublished unpublished: should_refuse, value;
hours_branch dated_branch and hours_day dated: branch_info, hours; closure dated: temporal_as_of, status; count dated:
current_value, count, forbid year; count_year dated: temporal_as_of, count, require_any year; contested_day
contested_day: contested_day, value, weight 0, forbid balance_min and balance_max.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proxy_kinds import KINDS  # noqa: E402
from proxy_kit import PLACEHOLDERS, ROOT, STATES, Ctx, fields, known_questions, near_duplicate, words  # noqa: E402

PROXY_DIR = ROOT / "eval" / "proxy"
KNOWN_SETS = (ROOT / "eval" / "public_eval.jsonl", ROOT / "eval" / "dev_extra.jsonl")
SEED_FAMILIES = ("paraphrase", "probe")
KIND_FIELDS = {"current": set(), "unpublished": set(), "tier_amount": {"amount"}, "as_of": {"date"},
               "contested_day": {"date"}, "change": {"date_from", "date_to"}, "dated": {"branch", "day", "year"},
               "dated_branch": {"branch"}, "unlisted_branch": {"branch"}, "prose": {"product"}}
SPECIAL = {"amount", "date", "date_from", "date_to", "branch", "day", "year"}


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_templates(data: Dict[str, Any], split: str) -> List[str]:
    """Every problem with a template file: unknown kinds or placeholders, missing fields, repeated ids, an id prefix
    that breaks the split's rule ("h-" for the holdout's ids, never for the proxy's), a date or amount the kind needs
    or forbids."""
    problems, seen = [], set()
    sets = data.get("name_sets", {})
    patterns = list(data.get("names", {}).values()) + list(data.get("attributes", {}).values())
    patterns += [p for names in sets.values() for p in names.values()]
    for family, spec in data.get("families", {}).items():
        kind = spec.get("kind")
        if kind not in KIND_FIELDS or not spec.get("category") or not spec.get("intent"):
            problems.append("family %s: needs a kind (%s), a category and an intent" % (family, ", ".join(KIND_FIELDS)))
            continue
        patterns += list(spec.get("names", {}).values())
        for tpl in spec.get("templates", []):
            tid, text = tpl.get("id", ""), tpl.get("text", "")
            patterns += list(tpl.get("attr_words", {}).values())
            used = set(fields(text))
            if not tid or tid in seen or tid.startswith("h-") != (split == "holdout"):
                problems.append("template %r: empty, repeated or against the %s id prefix rule" % (tid, split))
            if tpl.get("name_set", "") not in sets and "name_set" in tpl:
                problems.append("template %s: no name set %r" % (tid, tpl["name_set"]))
            if tpl.get("as_of", "text") not in ("text", "argument") or \
                    tpl.get("endpoints", "consecutive") not in ("consecutive", "to_latest"):
                problems.append("template %s: as_of is text or argument, endpoints consecutive or to_latest" % tid)
            seen.add(tid)
            if not used <= (PLACEHOLDERS - SPECIAL) | KIND_FIELDS[kind]:
                problems.append("template %s: placeholders %s do not belong to kind %s" % (tid, sorted(used), kind))
            dated_text = {"date"} if tpl.get("as_of", "text") == "text" else set()
            wants = {"tier_amount": {"amount"}, "as_of": dated_text, "contested_day": dated_text,
                     "change": {"date_from"} | ({"date_to"} if tpl.get("endpoints", "consecutive") == "consecutive"
                                                else set())}.get(kind, set())
            if not wants <= used or (kind == "change" and tpl.get("endpoints") == "to_latest" and "date_to" in used):
                problems.append("template %s: kind %s needs %s in its text" % (tid, kind, sorted(wants)))
    problems += ["pattern %r: only qualifier placeholders" % p for p in patterns if not set(fields(p)) <= set(STATES)]
    return problems


def seed_items(public: Dict[str, dict]) -> List[dict]:
    """The proxy's seeds: every paraphrase as its public original with the new question (a [question, as_of] pair
    brings its own as_of) and every probe as an item."""
    items = []
    for oid, questions in load_json(PROXY_DIR / "seeds" / "paraphrases.json")["paraphrases"].items():
        for k, entry in enumerate(questions, 1):
            question, as_of = (entry[0], entry[1]) if isinstance(entry, list) else (entry, public[oid].get("as_of"))
            item = dict(public[oid], id="para-%s-p%d" % (oid, k), question=question, as_of=as_of)
            item.update(family="paraphrase", template=None, route=None, key=None, origin=oid)
            items.append(item)
    probes = load_json(PROXY_DIR / "seeds" / "probes.json")
    rows = [("probe-%02d" % k, q, as_of, must, must_not, category, "p05 %s: %s" % (fam, cite))
            for k, (fam, q, as_of, must, must_not, category, cite) in enumerate(probes["p05"], 1)]
    rows += [("probe-chg-%d" % k, q, None, must, must_not, "change_between_snapshots", "p05b: " + cite)
             for k, (q, must, must_not, cite) in enumerate(probes["p05b"], 1)]
    for pid, q, as_of, must, must_not, category, origin in rows:
        items.append({"id": pid, "question": q, "as_of": as_of, "must_include": must, "must_not_include": must_not,
                      "category": category, "weight": 1.0, "expected_sources": [], "group": None, "family": "probe",
                      "template": None, "route": None, "key": None, "origin": origin})
    return items


def order_key(item: dict) -> Tuple[str, str, str, str]:
    return item["family"], item["template"] or item["id"], item["key"] or "", item["id"]


def finish(seeds: List[dict], made: List[dict], known: Sequence[Any]) -> Tuple[List[dict], List[Tuple[str, dict]]]:
    """(kept items in output order, dropped (reason, item) pairs): near-duplicates of a known question go, and of the
    items asking one (question, as_of) one stays when all agree, else the seeds only."""
    dropped: List[Tuple[str, dict]] = []
    slots: Dict[Tuple, List[dict]] = {}
    for item in seeds + sorted(made, key=order_key):
        if near_duplicate(item["question"], known):
            dropped.append(("near-duplicate", item))
        else:
            slots.setdefault((tuple(words(item["question"])), item["as_of"]), []).append(item)
    kept = []
    for members in slots.values():
        agree = len({(tuple(m["must_include"]), tuple(m["must_not_include"]), m["category"]) for m in members}) == 1
        stay = members[:1] if agree else [m for m in members if m["family"] in SEED_FAMILIES]
        kept += stay
        dropped += [("repeat" if agree else "contradiction", m) for m in members if m not in stay]
    return sorted(kept, key=order_key), dropped


def build_store() -> Any:
    """``solution.build()`` with every crawl under snapshots/ ingested; ingestion's stdout goes to stderr."""
    import solution
    from run_eval import load_snapshots

    ks = solution.build()
    with contextlib.redirect_stdout(sys.stderr):
        for snapshot in load_snapshots(ROOT / "snapshots"):
            ks.ingest(snapshot)
    return ks.store


def main(argv: Sequence[str] = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the proxy or the holdout eval set (see the module docstring).")
    ap.add_argument("--split", required=True, choices=("proxy", "holdout"))
    ap.add_argument("--templates", type=Path, help="the split's template file (required for --split holdout)")
    ap.add_argument("--out", type=Path, help="where the JSON lines go (default eval/proxy/<split>.jsonl)")
    args = ap.parse_args(argv)
    if args.templates is None:
        if args.split == "holdout":
            ap.error("--split holdout needs --templates: its own file, never the proxy's (Task 21)")
        args.templates = PROXY_DIR / "proxy_templates.json"
    templates = load_json(args.templates)
    problems = check_templates(templates, args.split)
    if problems:
        if args.split == "holdout":
            ap.error("holdout templates failed validation: %d problems (details suppressed)" % len(problems))
        ap.error("bad template file %s: %s" % (args.templates, "; ".join(problems)))
    universe = load_json(PROXY_DIR / "universe.json")
    public_rows = load_jsonl(KNOWN_SETS[0])
    known = [row["question"] for path in KNOWN_SETS for row in load_jsonl(path)]
    if args.split == "holdout":
        if not (PROXY_DIR / "proxy.jsonl").is_file():
            ap.error("eval/proxy/proxy.jsonl is missing: build the proxy split first")
        known += [row["question"] for row in load_jsonl(PROXY_DIR / "proxy.jsonl")]
    ctx = Ctx(build_store(), args.split, templates)
    made: List[dict] = []
    for family, spec in templates["families"].items():
        made += KINDS[spec["kind"]](ctx, family, spec, [tuple(pair) for pair in universe.get(family, [])])
    seeds = seed_items({row["id"]: row for row in public_rows}) if args.split == "proxy" else []
    kept, dropped = finish(seeds, made, known_questions(known))
    out = args.out or PROXY_DIR / (args.split + ".jsonl")
    out.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in kept), encoding="utf-8")
    counts: Dict[str, int] = {}
    for item in kept:
        counts[item["family"]] = counts.get(item["family"], 0) + 1
    print("build_proxy_set: %d %s items in %s; by family: %s" % (len(kept), args.split, out, ", ".join(
        "%s %d" % (family, counts.get(family, 0)) for family in sorted(set(counts) | set(templates["families"])))),
        file=sys.stderr)
    for reason in ("near-duplicate", "repeat", "contradiction"):
        ids = [item["id"] for why, item in dropped if why == reason]
        if ids:
            detail = ": " + " ".join(ids) if args.split == "proxy" else ""
            print("build_proxy_set: dropped %d as %s%s" % (len(ids), reason, detail), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
