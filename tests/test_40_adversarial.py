# tests/test_40_adversarial.py
import json, os, re, subprocess, sys, time

import pytest
from contract import Page, Snapshot, Source

QUESTION = "What is the APY on Dupaco's 17-month special certificate?"

def test_no_lazy_work_in_answer(ks_full):
    t = time.perf_counter(); ks_full.answer("What is the APY on Dupaco's 17-month special certificate?")
    assert time.perf_counter() - t < 0.05

def test_repeat_and_paraphrase_identical(ks_full):
    a = ks_full.answer("What is the APY on Dupaco's 17-month special certificate?")
    b = ks_full.answer("How much does the 17 month certificate special yield?")
    assert a.text == ks_full.answer("What is the APY on Dupaco's 17-month special certificate?").text and a.text == b.text

def test_hostile_inputs_never_raise(ks_full):
    for q, a in ((None, None), ("", "2026-05-31"), ("9" * 100_000, None), ("rate?", "garbage"), (42, None)):
        assert ks_full.answer(q, as_of=a).confident is False

def test_ingest_after_answer_refinalises(real_snapshots):
    # The brief ran this on harness/selftest, whose pages ("6-month certificate APY: 2.95%") hold no table row and no
    # "x% APY" phrase, so the Phase 2 rules extractor reads no fact there. Crawl 03 lists the 17-month special at
    # 3.85% and crawl 05 at 4.10%: a stale cache entry or an unfinalised store would leave the first value standing.
    import solution; ks = solution.build()
    ks.ingest(real_snapshots[2]); first = ks.answer("What is the APY on Dupaco's 17-month special certificate?").text
    ks.ingest(real_snapshots[4]); second = ks.answer("What is the APY on Dupaco's 17-month special certificate?").text
    assert first != second and "3.85%" in first and "4.10%" in second

@pytest.mark.parametrize("eval_set, snapshots", [
    ("harness/selftest/eval.jsonl", "harness/selftest/snapshots"),  # the brief's case: every answer is a refusal
    ("eval/public_eval.jsonl", "snapshots"),  # real facts, so resolve and compose run on every item
])
def test_determinism_across_hash_seeds(tmp_path, eval_set, snapshots):
    outs = []
    for seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "OPENAI_API_KEY": "sk-fake"}
        subprocess.run([sys.executable, "scripts/_guarded_run_eval.py", "--submission", "submission", "--eval", eval_set, "--snapshots", snapshots, "--out", str(tmp_path / seed), "--repeat-sample", "0"], env=env, check=True, capture_output=True)
        rows = [json.loads(l) for l in (tmp_path / seed / "per_question.jsonl").read_text().splitlines()]
        outs.append([{k: v for k, v in r.items() if k != "latency_s"} for r in rows])
    assert outs[0] == outs[1]

def test_no_sdk_modules_and_no_sockets_after_real_run(tmp_path):
    code = "import runpy,sys,socket; socket.socket=None; sys.argv=['run_eval','--submission','submission','--eval','harness/selftest/eval.jsonl','--snapshots','harness/selftest/snapshots','--out',%r,'--repeat-sample','0']; runpy.run_path('harness/run_eval.py', run_name='__main__'); print(sorted(m for m in sys.modules if m.split('.')[0] in ('openai','anthropic','google','requests','httpx')))" % str(tmp_path / "o")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert r.stdout.strip().endswith("[]")

def test_answer_before_any_ingest_is_a_refusal():
    import solution
    from scoring import _numbers
    ks = solution.build()
    arm = "What is your rate on a 7/1 adjustable-rate mortgage?"
    for question in (QUESTION, arm):
        a = ks.answer(question)
        assert a.confident is False and _numbers(a.text) <= _numbers(question)
    assert ks.conflicts() == [] and ks.explain(QUESTION)["winner"] is None

def _uncached(ks, question, as_of=None):
    """parse -> resolve -> render straight through the kb modules, then the facade's curated-conflict note (``with_note``
    on the index ingest built): an answer no cache can have touched; parse gets the reference date the facade passes
    (the newest crawl's day), so a month written without a year resolves alike."""
    from kb.compose import render
    from kb.conflicts import with_note
    from kb.question import parse
    from kb.resolve import resolve
    crawls = ks.store.snapshots()
    q = parse(question, as_of, ks.registry, ks.config.max_question_chars, reference_date=crawls[-1][1] if crawls else None)
    plan = resolve(q, ks.store, ks.registry)
    return with_note(render(plan), plan, ks._notes)

def test_answer_and_conflicts_never_build_indexes(ks_full, monkeypatch):
    # finalize() is the store's only index build, and ingest() has run it already
    from kb.store import FactStore
    def build(self): raise AssertionError("finalize() outside ingest()")
    monkeypatch.setattr(FactStore, "finalize", build)
    a = ks_full.answer("What was the APY on the 17-month certificate special as of August 2026?")  # asked nowhere else
    assert a.confident and "3.95%" in a.text
    assert len(ks_full.conflicts()) == len(json.load(open("submission/data/conflicts_curated.json"))["conflicts"])

# Twins share a canonical key but not an answer: the resolver also reads the question's numbers (the yes/no verdict,
# the refusal's digits) and its words (an explicit "personal" filters a list, the refusal quotes the question), and a
# malformed as_of parses to the key of no as_of. Each pair is asked in the order in which a stale hit would show.
TWINS = [
    (("Is the Share Savings APY 0.20%?", None), ("Is the Share Savings APY 0.35%?", None)),
    (("What is your rate on a 7/1 adjustable-rate mortgage?", None), ("What is your rate on a 10/1 adjustable-rate mortgage?", None)),
    (("What credit cards do you offer and what are their APRs?", None), ("What personal credit cards do you offer and their APRs?", None)),
    ((QUESTION, None), (QUESTION, "garbage")),
]

def test_cache_never_changes_an_answer(ks_full, public_items):
    from kb.question import parse
    for first, second in TWINS:
        assert parse(*first, ks_full.registry).canonical_key == parse(*second, ks_full.registry).canonical_key
    asked = [ask for pair in TWINS for ask in pair] + [(it["question"], it.get("as_of")) for it in public_items] + [
        ("What was the 10-month fixed jumbo special certificate rate in May?", None)]  # a month without a year
    for _ in range(2):  # the second pass is served from the cache
        for question, as_of in asked:
            assert ks_full.answer(question, as_of) == _uncached(ks_full, question, as_of), (question, as_of)
    assert ks_full.answer("Is the Share Savings APY 0.20%?").text.startswith("Yes.")
    assert ks_full.answer("Is the Share Savings APY 0.35%?").text.startswith("No.")
    assert "7" not in ks_full.answer("What is your rate on a 10/1 adjustable-rate mortgage?").text
    assert len(ks_full.answer("What personal credit cards do you offer and their APRs?").text.splitlines()) == 2
    assert ks_full.answer(QUESTION, "garbage").confident is False

def test_cached_answers_are_never_shared(ks_full):
    a = ks_full.answer(QUESTION)
    a.text = "tampered"; a.sources.append(Source(url="https://example.test/")); a.sources[0].url = "https://example.test/x"
    b = ks_full.answer(QUESTION)
    assert b is not a and b == _uncached(ks_full, QUESTION) and "4.10%" in b.text

def test_snapshot_order_does_not_matter(ks_full, real_snapshots, public_items, capsys):
    import solution; ks = solution.build()
    capsys.readouterr()
    for snapshot in reversed(real_snapshots):
        ks.ingest(snapshot)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("kb: ")]
    assert len(lines) == len(real_snapshots)
    for line, s in zip(lines, reversed(real_snapshots)):
        pattern = r"kb: ingested %s pages=%d facts=\d+ unmapped_rows=0 ignored_rows=\d+ in \d+\.\d\d s" % (re.escape(s.snapshot_id), len(s.pages))
        assert re.fullmatch(pattern, line), line
    assert ks.store.snapshots() == ks_full.store.snapshots()
    for it in public_items:
        assert ks.answer(it["question"], it.get("as_of")) == ks_full.answer(it["question"], it.get("as_of")), it["id"]

def test_pages_without_url_or_markdown_are_skipped_and_a_crawl_is_added_once(real_snapshots):
    import solution; ks = solution.build()
    latest = real_snapshots[4]
    rates = next(p for p in latest.pages if p.url.rstrip("/").endswith("dupaco.com/rates"))
    broken = [Page(url=None, title="", markdown="| a | b |", fetched_at=rates.fetched_at),
              Page(url=rates.url, title="", markdown=None, fetched_at=rates.fetched_at)]
    snapshot = Snapshot(latest.snapshot_id, latest.taken_on, broken + [rates])
    ks.ingest(snapshot)
    counts, stored = dict(ks.ingested[latest.snapshot_id]), sum(map(len, ks.store.by_key[latest.snapshot_id].values()))
    ks.ingest(snapshot)  # the same crawl again adds nothing
    assert counts["pages"] == 1 and counts["skipped_pages"] == 2 and counts["facts"] == stored > 0
    assert ks.ingested[latest.snapshot_id] == counts and sum(map(len, ks.store.by_key[latest.snapshot_id].values())) == stored
    assert "4.10%" in ks.answer(QUESTION).text

def _rates(snapshot):
    return next(p for p in snapshot.pages if p.url.rstrip("/").endswith("dupaco.com/rates"))

def test_a_malformed_url_is_skipped_not_raised(real_snapshots):
    # urlsplit raises ValueError("Invalid IPv6 URL") here, and harness/run_eval.py does not guard ingest()
    import solution; ks = solution.build()
    latest = real_snapshots[4]
    bad = Page(url="https://[bad/x", title="", markdown="| a | b |", fetched_at=latest.taken_on)
    ks.ingest(Snapshot(latest.snapshot_id, latest.taken_on, [bad, _rates(latest)]))
    counts = ks.ingested[latest.snapshot_id]
    assert counts["skipped_pages"] == 1 and counts["pages"] == 1 and counts["facts"] > 0
    assert "4.10%" in ks.answer(QUESTION).text

def test_taken_on_datetime_is_cut_to_its_date_and_a_bad_one_skips_the_crawl(real_snapshots, capsys):
    import solution; ks = solution.build()
    june, latest = real_snapshots[2], real_snapshots[4]
    ks.ingest(Snapshot(june.snapshot_id, june.taken_on + "T05:07:31.583Z", [_rates(june)]))
    ks.ingest(Snapshot(latest.snapshot_id, latest.taken_on + "T00:00:00", [_rates(latest)]))
    crawls = [(june.snapshot_id, june.taken_on), (latest.snapshot_id, latest.taken_on)]
    assert ks.store.snapshots() == crawls and "4.10%" in ks.answer(QUESTION).text
    capsys.readouterr()
    ks.ingest(Snapshot("06_bad_date", "next tuesday", [_rates(latest)]))
    err = capsys.readouterr().err
    assert ks.store.snapshots() == crawls and "06_bad_date" not in ks.ingested
    assert len([line for line in err.splitlines() if "06_bad_date" in line]) == 1

def test_the_legacy_url_shape_is_one_rule_for_classify_and_the_alias_pass(real_snapshots):
    import solution
    from kb.normalize import canonical_url
    from kb.pagetype import classify, legacy_shaped
    for url in ("https://www.dupaco.com/dupacodaily", "https://www.dupaco.com/dupacodaily/2017/06/post.html",
                "https://www.dupaco.com/2018/09/25/slug/"):
        assert legacy_shaped(url) and classify(url, "") == "legacy_alias", url
    assert legacy_shaped("https://www.dupaco.com/checking/") and not legacy_shaped("https://www.dupaco.com/checking")
    latest = real_snapshots[4]
    savings = next(p for p in latest.pages if canonical_url(p.url) == "https://www.dupaco.com/personal/savings-account")
    copy = Page(url="https://www.dupaco.com/dupacodaily", title="", markdown=savings.markdown, fetched_at=savings.fetched_at)
    ks = solution.build(); ks.ingest(Snapshot(latest.snapshot_id, latest.taken_on, [savings, copy]))
    copied = [f for facts in ks.store.by_key[latest.snapshot_id].values() for f in facts if f.source.url == copy.url]
    assert copied and {(f.source.page_type, f.source.canonical_url) for f in copied} == {("legacy_alias", canonical_url(savings.url))}

def test_hostile_questions_refuse_fast_with_no_new_digits(ks_full):
    from scoring import _numbers
    for q in (None, 42, "", "   ", "12345", "$9," * 34_000, "7/1 " * 25_000):
        t = time.perf_counter(); a = ks_full.answer(q)
        assert time.perf_counter() - t < 1.0 and a.confident is False, repr(q)[:40]
        assert _numbers(a.text) <= _numbers(q if isinstance(q, str) else ""), repr(q)[:40]

def test_unexpected_errors_become_refusals(ks_full, monkeypatch, capsys):
    import kb.errors, kb.system
    monkeypatch.setattr(kb.errors, "_warned", set())
    class Surprise(Exception): pass
    for error, question in ((ValueError("bad row"), "What is the APY on the 12-month regular certificate?"),
                            (Surprise("odd"), "What is the APY on the 24-month regular certificate?")):
        def fail(*args, **kwargs): raise error
        monkeypatch.setattr(kb.system, "resolve", fail)
        a = ks_full.answer(question)
        assert a.confident is False and "can't confirm" in a.text and not any(ch.isdigit() for ch in a.text)
    err = capsys.readouterr().err
    assert "[KB-E06] unexpected ValueError" in err and "Surprise" in err and "24-month regular certificate" in err

def test_explain_shows_the_work(ks_full):
    from kb.question import parse
    info = ks_full.explain(QUESTION)
    json.dumps(info)  # string keys and JSON values only: scripts/ask.py prints it
    assert info["canonical_key"] == parse(QUESTION, None, ks_full.registry).canonical_key
    assert info["snapshot_id"] == "05_2026-09-28_latest" and info["answer"] == ks_full.answer(QUESTION).text
    assert set(info["timings_ms"]) == {"parse", "resolve", "render"} and info["dropped_sentences"] == []
    assert [c["rank"] for c in info["candidates"]] == list(range(1, len(info["candidates"]) + 1))
    assert info["winner"] == info["candidates"][0] and info["winner"]["value_text"] == "4.10%"
    refused = ks_full.explain("What is your rate on a 7/1 adjustable-rate mortgage?")
    assert refused["candidates"] == [] and refused["winner"] is None and refused["answer"].startswith("I can't confirm")
    assert "website" not in refused["answer"]
    bad_date = ks_full.explain(QUESTION, "garbage")  # as_of None alone would hide why it refused
    json.dumps(bad_date)
    assert info["as_of_error"] is False and bad_date["as_of_error"] is True and bad_date["winner"] is None

def test_long_question_is_cut_then_answered_and_bad_input_is_reported(ks_full, monkeypatch, capsys):
    import kb.errors
    monkeypatch.setattr(kb.errors, "_warned", set())
    assert ks_full.answer(QUESTION + " " * 1000 + "Or is it 9.99%?") == ks_full.answer(QUESTION)  # the tail is cut
    assert ks_full.answer(QUESTION, as_of="31/31/2026").confident is False
    err = capsys.readouterr().err
    assert "[KB-E05]" in err and "answered" in err and "[KB-E04]" in err
