# tests/test_31_compose_p3.py
import json
from dataclasses import replace
from pathlib import Path

from conftest import make_fact, single_plan
from kb.compose import render
from kb.lint import lint
from kb.question import parse
from kb.registry import Registry
from kb.resolve import EARLIEST_NOTE, join_notes, resolve
from kb.types import ClaimType
R = Registry.load()
BARE = "10 Month Fixed Certificate Special: 3.90% APY."

def test_compose_is_split_and_reexports():
    from kb.compose import HOURS_NOTE, RENDERERS, label, lint, product_names, refusal, render, render_with_dropped, strip_residue
    import kb.labels, kb.lint
    lines = {n: len(Path("submission/kb", n).read_text().splitlines()) for n in ("compose.py", "labels.py", "lint.py")}
    assert lines["compose.py"] <= 350 and lines["labels.py"] <= 170 and lines["lint.py"] <= 120, lines  # 350: Task 4's caveat

def test_as_of_guard_uses_dates_not_the_note():
    f = make_fact("cert_special", "apy", "3.90%", term_months=10, special=True)
    plan = replace(single_plan("value", f, frozenset({("%", 3.9), ("", 2026.0)})), as_of="2026-09-15",
                   first_crawl="2026-05-12", crawl_date="2026-09-28")
    assert render(plan).text == "As of September 2026, " + BARE
    assert render(replace(plan, conflict_note=EARLIEST_NOTE)).text == "As of September 2026, " + BARE
    assert render(replace(plan, as_of="2026-01-15", conflict_note=EARLIEST_NOTE)).text == BARE + "\n" + EARLIEST_NOTE  # before the first crawl: no prefix, and the resolver's note follows the text (User decision 1)
    assert render(replace(plan, crawl_date="2026-08-27")).text == BARE  # the plan's crawl date wins over the snapshot id's
    assert render(replace(plan, as_of="2026-05-12", crawl_date="2026-05-12")).text == "As of May 2026, " + BARE  # the first crawl's own day

def test_resolver_sets_crawl_dates(store_full):
    p = resolve(parse("What is the APY on the 10-month certificate special?", "2026-01-15", R), store_full, R)
    assert (p.first_crawl, p.crawl_date, p.conflict_note) == ("2026-05-12", "2026-05-12", EARLIEST_NOTE)
    r = resolve(parse("What is your rate on a 7/1 adjustable-rate mortgage?", None, R), store_full, R)
    assert r.confident is False and r.first_crawl == "2026-05-12"

def test_compose_reads_no_note_string_and_notes_join():
    assert "EARLIEST_NOTE" not in Path("submission/kb/compose.py").read_text()
    assert join_notes(None, "") is None and join_notes(EARLIEST_NOTE, None) == EARLIEST_NOTE
    assert join_notes(EARLIEST_NOTE, "Sources disagree.") == EARLIEST_NOTE + " Sources disagree."

def test_pre_crawl_answers_carry_the_caveat_sentence(ks_full):  # User decision 1
    from kb.normalize import number_tokens
    a = ks_full.answer("What was the 10-month fixed jumbo special certificate APY?", "2026-04-30")
    assert "3.90%" in a.text and a.text.endswith(EARLIEST_NOTE) and a.conflict_note.startswith(EARLIEST_NOTE)  # a curated note (Task 10's with_note) may join after it
    assert number_tokens(a.text) == number_tokens(a.text[:-len(EARLIEST_NOTE)])

def test_strict_lint_checks_bare_numbers():
    text = "Lobby hours at the Platteville branch: Saturday 9 a.m.–noon.\nFounded in 1948."
    permitted = frozenset({("", 9.0)})
    assert lint(text, permitted, strict=True) == ("Lobby hours at the Platteville branch: Saturday 9 a.m.–noon.", ["Founded in 1948."])
    assert lint(text, permitted)[1] == []  # rules plans keep the old behaviour (pin)

def test_strict_plan_keeps_label_numbers():
    f = make_fact("branch", "lobby_hours", "9 a.m.–noon", extractor="prose", claim=ClaimType.ASSERTION, unit="text",
                  branch_name="highway 151, platteville", day="saturday")
    plan = replace(single_plan("hours", f, frozenset({("", 9.0), ("", 151.0)})), strict_numbers=True)
    assert "9 a.m.–noon" in render(plan).text and "151" in render(plan).text

def test_no_prose_fact_carries_a_trap_token(store_full, public_items):
    import sys; sys.path.insert(0, "scripts"); from trap_census import collisions
    dev = [json.loads(l) for l in open("eval/dev_extra.jsonl") if l.strip()]
    allowed = json.loads(open("tests/fixtures/trap_allowlist.json").read())
    rows = collisions(store_full, public_items + dev)  # (pid|attr, value_text, token, item id)
    assert [r for r in rows if r[0] + "|" + r[2] not in allowed] == []

def _echo_plans():  # one confident plan per renderer, each grounded so its template runs
    from kb.resolve import PAST
    apy, old = make_fact("share_savings", "apy", "0.20%"), make_fact("share_savings", "apy", "0.25%", snapshot_id="04_2026-08-27_rebaseline")
    mm = make_fact("money_market_investors_choice", "apy", "0.50%")
    lobby = [make_fact("branch", "lobby_hours", v, extractor="prose", claim=ClaimType.ASSERTION, unit="text", published="2024-04-26",
                       row=r, branch_name=b, day="saturday") for b, v, r in (("waukee", "9 a.m.–noon", 1), ("grimes", "Closed", 2))]
    count = make_fact("branch_count", "count", "22 branch offices", extractor="prose", claim=ClaimType.ASSERTION, unit="count",
                      published="2026-04-06")
    text = dict(unit="text", claim=ClaimType.ASSERTION)
    one = {"value": apy, "yes_no": apy, PAST: old, "count": count, "url": make_fact("membership", "url", "https://www.dupaco.com/about/join", **text),
           "how_to": make_fact("membership", "url", "https://www.dupaco.com/about/join", **text),
           "status": make_fact("branch", "status", "Closed", unit="text", claim=ClaimType.STATUS, branch_name="hy-vee"),
           "address": make_fact("branch", "address", "11375 Oldenburg Ln., Galena, IL, 61036", branch_name="oldenburg ln., galena", **text),
           "phone": make_fact("membership", "phone", "800-373-7600", **text), "routing": make_fact("membership", "routing_number", "273976369", **text)}
    many = {"list": (apy, mm), "change": (old, apy), "hours": tuple(lobby)}
    plans = {intent: single_plan(intent, f, frozenset({("%", 0.2), ("%", 0.25), ("", 22.0)})) for intent, f in one.items()}
    for intent, facts in many.items():
        permitted = frozenset({("%", 0.2), ("%", 0.25), ("%", 0.5), ("", 9.0)})
        plans[intent] = replace(single_plan(intent, facts[0], permitted), facts=facts, sources=tuple(f.source for f in facts),
                                snapshot_id=facts[-1].source.snapshot_id)  # a change plan's snapshot is the latest crawl
    plans["hours"] = replace(plans["hours"], strict_numbers=True)
    plans["count"] = replace(plans["count"], strict_numbers=True)
    prose = dict(extractor="prose", unit="text", published="2025-06-20", branch_name="hy-vee")  # Task 13: a closure, an alternative
    closure = make_fact("branch", "closure_date", "March 31, 2026", claim=ClaimType.STATUS, event="2026-03-31", **prose)
    plans["closure"] = single_plan("status", closure, frozenset({("", 31.0), ("", 2026.0)}), strict_numbers=True)
    alternatives = make_fact("branch", "alternatives", "Key West and Sycamore Street", claim=ClaimType.ASSERTION, **prose)
    plans["alternatives"] = single_plan("value", alternatives, strict_numbers=True)
    return plans

def test_templates_never_echo_the_question():  # (pin) every renderer; strip_residue keeps the probe, so an echo would show
    for probe in ("Do all branches keep the same <b>{x}* zebraquokka 271176899 hours open?",  # hours and status verdicts
                  "Do all branches keep the same <b>{x}* zebraquokka hours open?"):  # digit-free: no strict lint drops an echo
        for intent, plan in _echo_plans().items():
            a = render(replace(plan, question=probe))
            assert a.confident and "zebraquokka" not in a.text and "271176899" not in a.text, (intent, a.text)

def test_templates_hold_no_forbidden_assistant_phrasing():  # (pin) gap research #6
    import ast
    from scoring import contains
    items = [json.loads(l) for l in open("eval/public_eval.jsonl") if l.strip()]
    phrases = sorted({t for it in items for t in it["must_not_include"] if " " in t.strip() and not any(c.isdigit() for c in t)})
    assert {"don't have that detail", "unable to find", "in these facts", "Which certificate term would you like",
            "ZIP code", "member number"} <= set(phrases)
    found = []
    for name in ("compose.py", "compose_prose.py", "labels.py", "plans.py"):  # compose_prose.py appears in Task 12; plans.py holds the pre-crawl note
        path = Path("submission/kb", name)
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
        found += [(name, p) for p in phrases for s in strings if contains(s, p)]
    assert found == []

def _hours(**quals):  # a prose lobby-hours fact, as kb.extract_prose reads one
    return make_fact("branch", "lobby_hours", "9 a.m.–noon", extractor="prose", claim=ClaimType.ASSERTION, unit="text", **quals)

def test_bounds_permit_the_year_and_branch_name_numbers():  # what a strict plan's labels print
    from kb.plans import _bounds
    count = make_fact("employee_count", "count", "1,100", extractor="prose", claim=ClaimType.ASSERTION, unit="count", year=2023)
    assert _bounds(_hours(branch_name="highway 151, platteville", day="saturday")) == {("", 151.0)}
    assert _bounds(count) == {("", 2023.0)} and _bounds(_hours(branch_name="platteville")) == set()

def test_strict_render_drops_an_unpermitted_bare_number():
    plan = single_plan("hours", _hours(branch_name="highway 151, platteville", day="saturday"), frozenset({("", 9.0)}))
    assert "151" in render(plan).text  # not strict: bare numbers pass, as in every rules plan
    assert render(replace(plan, strict_numbers=True)).confident is False  # strict: the line holding 151 goes, nothing grounds

def test_resolver_sets_strict_numbers_from_the_extractors(store_full):
    hours = resolve(parse("What are the lobby hours at the Platteville branch?", None, R), store_full, R)
    rate = resolve(parse("What is the APY on the 10-month certificate special?", None, R), store_full, R)
    refused = resolve(parse("What is your rate on a 7/1 adjustable-rate mortgage?", None, R), store_full, R)
    assert {f.extractor for f in hours.facts} == {"prose"} and hours.strict_numbers is True
    assert rate.facts and rate.strict_numbers is False and refused.strict_numbers is False

def test_trap_census_reads_prose_and_curated_facts_only(monkeypatch, capsys):
    import sys; sys.path.insert(0, "scripts"); import trap_census
    from types import SimpleNamespace
    from kb.store import FactStore
    store = FactStore()
    for sid in ("04_2026-08-27_aug", "05_2026-09-28_latest"):  # the same facts in two crawls give each row once
        store.add(sid, sid[3:13], [make_fact("employee_count", "count", "2,020 employees", extractor="curated", unit="count",
                                             snapshot_id=sid), _hours(snapshot_id=sid, branch_name="cedar falls"),
                                   make_fact("share_savings", "apy", "2020", snapshot_id=sid)])  # rules: no census row
    store.finalize()
    items = [{"id": "x-1", "must_not_include": ["2020", "noon"]}, {"id": "x-2", "must_not_include": ["9 a.m."]}]
    rows = [("branch|lobby_hours", "9 a.m.–noon", "9 a.m.", "x-2"), ("branch|lobby_hours", "9 a.m.–noon", "noon", "x-1"),
            ("employee_count|count", "2,020 employees", "2020", "x-1")]
    assert trap_census.collisions(store, items) == rows
    monkeypatch.setattr(trap_census, "build_system", lambda: SimpleNamespace(store=store))
    monkeypatch.setattr(trap_census, "load_items", lambda: items)
    assert trap_census.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == ["\t".join(r[0].split("|") + list(r[1:])) for r in rows]
    assert out[3:] == ["trap_census: 3 collisions; 4 prose or curated facts, 3 must_not_include tokens, 2 items"]
