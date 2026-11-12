# tests/test_30_compose.py
from kb.compose import render, lint, strip_residue, refusal
from kb.resolve import resolve
from kb.question import parse
from kb.registry import Registry
from scoring import _numbers, REFUSAL_RE, contains
R = Registry.load()
def _answer(store, q, as_of=None): return render(resolve(parse(q, as_of, R), store, R))

def test_value_template_has_unit_and_label(store_full):
    a = _answer(store_full, "What is the APY on Dupaco's 17-month special certificate?")
    assert contains(a.text, "4.10%") and "17 Month Fixed Certificate Special" in a.text and a.sources[0].url.startswith("https://www.dupaco.com/")

def test_lint_drops_sentence_with_stray_number():
    text, dropped = lint("The 60-month APR is 5.39%. The calculator shows 5.34%.", frozenset({("%", 5.39)}))
    assert text == "The 60-month APR is 5.39%." and dropped == ["The calculator shows 5.34%."]

def test_refusals_add_no_digits_and_match_regex(store_full, public_items):
    for it in public_items:
        if it["category"] == "should_refuse":
            a = _answer(store_full, it["question"], it.get("as_of"))
            assert a.confident is False and REFUSAL_RE.search(a.text) and _numbers(a.text) <= _numbers(it["question"])

def test_yes_no_does_not_echo_question_trap(store_full):
    a = _answer(store_full, "Is the highest Share Savings APY 0.35%?")
    assert a.text.startswith(("Yes.", "No.")) and contains(a.text, "0.20") and not contains(a.text, "0.35%")

def test_no_markdown_residue(store_full, public_items):
    for it in public_items:
        t = _answer(store_full, it["question"], it.get("as_of")).text
        assert not any(ch in t for ch in "{<*") and "\\r\\n" not in t

# pins beyond the brief's five: the controller rulings for the composer (sources, yes/no, change, dates, lint)
from dataclasses import dataclass, replace
from typing import Optional
from kb.compose import label, product_names
from kb.resolve import EARLIEST_NOTE
from kb.types import AnswerPlan
from conftest import make_fact, single_plan

def _plan(store, q, as_of=None): return resolve(parse(q, as_of, R), store, R)

@dataclass(frozen=True)
class _Asked(AnswerPlan):  # AnswerPlan.question (wave A passes q.raw_span), so the C3 pins run before and after it lands
    question: Optional[str] = None

def _with_question(plan, q): return _Asked(**{**vars(plan), "question": q})  # vars(plan) holds "question" once the field lands
def _asked(store, q): return _with_question(_plan(store, q), q)

def test_sources_preserve_each_quote_and_rate_rows_carry_their_apr(store_full):
    p = _plan(store_full, "Can you tell me the interest rate for a 30-year mortgage?")
    a = render(p)
    urls = [s.url for s in a.sources]
    triples = [(s.url, s.snapshot_id, s.quote) for s in a.sources]
    assert triples == list(dict.fromkeys((s.citation_url or s.canonical_url, s.snapshot_id, s.quote) for s in p.sources))
    assert len(set(urls)) > 1  # first seen first, including distinct evidence from one page
    assert "https://www.dupaco.com/personal/loans/home-loans" in urls  # a copy of the winning row earns the credit
    assert "30-Year Fixed Home Loans - Purchase, $100,000 or less: 7.13% rate (7.27% APR)." in a.text.splitlines()

def test_yes_no_answers_from_the_plan_and_never_states_the_claim(store_full):
    assert _answer(store_full, "Do you have a 17-month CD?").text == "Yes. 17 Month Fixed Certificate Special: 4.10% APY."
    assert _answer(store_full, "Is the highest Share Savings APY 0.20%?").text == "Yes. Share Savings, $25,000 or more: 0.20% APY."
    assert _answer(store_full, "Is the highest Share Savings APY 0.35%?").text == "No. Share Savings, $25,000 or more: 0.20% APY."
    assert _answer(store_full, "Is the APY on $15,000 in Share Savings 0.15%?").text.startswith("Yes.")  # the amount is no claim

def test_yes_no_claims_meet_the_rows_own_value_and_comparisons_get_no_verdict(store_full):
    rate = make_fact("mortgage_purchase", "rate", "7.13%", program="purchase", term_months=360)
    apr = make_fact("mortgage_purchase", "apr", "7.27%", program="purchase", term_months=360)  # the rate's APR companion
    plan = AnswerPlan("yes_no", (rate, apr), frozenset({("%", 7.13), ("%", 7.27), ("", 30.0), ("", 2026.0)}), (rate.source,),
                      True, None, rate.source.snapshot_id)
    row = "30-Year Fixed Home Loans - Purchase: 7.13% rate (7.27% APR)."
    def ask(q, p=plan): return render(_with_question(p, q)).text
    assert ask("Is the 30-year rate 7.27%?") == "No. " + row  # the APR beside the rate is no match for a claimed rate
    assert ask("Is the 30-year rate 7.13%?") == "Yes. " + row
    assert render(plan).text == "Yes. " + row  # a plan without the question text: today's reading of permitted_values
    for q in ("Is the 30-year rate above 7%?", "Is it below 8%?", "Is it over 7%?", "Is it under 8%?", "Is it more than 7%?",
              "Is it less than 8%?", "Is it at least 7%?", "Is it at most 8%?", "Is it higher than 7%?", "Is it LOWER THAN 8%?"):
        assert ask(q) == row, q  # a comparison: the grounding value alone, no verdict word
    assert ask("Is the overdraft rate 7.13%?") == "Yes. " + row and ask("Do you understand rates at 7.13%?") == "Yes. " + row
    dated = replace(plan, as_of="2026-09-15")
    assert ask("Is the rate above 7%?", dated) == "As of September 2026, " + row and ask("Is the rate 7.27%?", dated) == "No. As of September 2026, " + row
    below = render(_asked(store_full, "Is the auto loan APR below 12%?")).text  # real-store plans with the question attached
    assert below.splitlines()[0] == "48 Month Auto Loan, 2024-2027 model years: as low as 5.19% APR." and not contains(below, "12%")
    q = "Is the 30-year fixed mortgage rate for loans of $100,000 or less 7.27%?"
    assert render(_asked(store_full, q)).text == "No. 30-Year Fixed Home Loans - Purchase, $100,000 or less: 7.13% rate (7.27% APR)."
    assert render(_asked(store_full, "Is the Share Savings APY 0.20%?")).text.startswith("Yes. ")
    no = render(_asked(store_full, "Is the Share Savings APY 0.35%?")).text
    assert no.startswith("No. ") and not contains(no, "0.35")

def test_list_enumerates_every_card_and_keeps_digit_names(store_full):
    a = _answer(store_full, "What credit cards do you offer and what are their APRs?")
    assert a.text.splitlines() == ["Platinum Visa: 12.50% – 19.50% APR.", "Rewards Visa: 15.50% – 21.00% APR.",
                                   "Business Platinum Visa: 15.50% APR.", "Business Rewards Visa: 20.50% APR."]
    rows = _answer(store_full, "Provide current checking account interest rates").text.splitlines()
    assert "1st Rate Checking, $5,000 to $24,999.99: 2.50% APY." in rows  # the lint keeps a digit in a product name

def test_change_renders_two_dated_values_or_unchanged(store_full):
    a = _answer(store_full, "How did the 30-year fixed mortgage rate (loans of $100,000 or less) change between the May 12 and September 28, 2026 crawls?")
    assert a.text == ("Between May 12, 2026 and September 28, 2026:\n"
                      "30-Year Fixed Home Loans - Purchase, $100,000 or less: it was 5.875% rate (6.010% APR); it is 7.13% rate (7.27% APR).")
    b = _answer(store_full, "Has the 36-month personal loan APR changed since May 2026?")  # dev-010, dated once in the header
    assert b.text == "Between May 19, 2026 and September 28, 2026:\n36 Month Personal Loan: unchanged at as low as 10.49% APR."

def test_dates_render_only_when_the_plan_permits_them():
    old = make_fact("personal_loan", "apr", "9.99%", term_months=24)
    old = replace(old, source=replace(old.source, snapshot_id="02_2026-05-19_recrawl"))
    new = make_fact("personal_loan", "apr", "10.49%", term_months=24)
    days = frozenset({("%", 9.99), ("%", 10.49), ("", 19.0), ("", 28.0), ("", 2026.0)})
    plan = AnswerPlan("change", (old, new), days, (), True, None, new.source.snapshot_id)
    assert render(plan).text == "Between May 19, 2026 and September 28, 2026:\n24 Month Personal Loan: it was 9.99% APR; it is 10.49% APR."
    undated = replace(plan, permitted_values=frozenset({("%", 9.99), ("%", 10.49)}))
    assert render(undated).text == "24 Month Personal Loan: in an earlier crawl it was 9.99% APR; in the latest crawl it is 10.49% APR."
    assert render(replace(plan, facts=(new,))).text == "24 Month Personal Loan: on September 28, 2026 it is 10.49% APR."  # one side only
    one_day = replace(plan, permitted_values=days - {("", 19.0)})  # one date unpermitted: no header, each row as before
    assert render(one_day).text == "24 Month Personal Loan: in an earlier crawl it was 9.99% APR; on September 28, 2026 it is 10.49% APR."

def test_change_header_dates_both_crawls_once_and_keeps_every_number():
    def earlier(f): return replace(f, source=replace(f.source, snapshot_id="04_2026-08-27_rebaseline"))
    old_tier = make_fact("auto_loan", "apr", "4.99% APR", term_months=48, model_year_min=2023, model_year_max=2026)
    new_tier = make_fact("auto_loan", "apr", "5.19% APR", term_months=48, model_year_min=2024, model_year_max=2027)
    up = [make_fact("auto_loan", "apr", v, term_months=48, model_year_min=0, model_year_max=2016) for v in ("8.39% APR", "8.59% APR")]
    flat = make_fact("personal_loan", "apr", "10.49%", term_months=36)
    facts = (earlier(old_tier), earlier(up[0]), earlier(flat), up[1], flat, new_tier)  # the from-crawl's rows first
    permitted = frozenset({("%", 4.99), ("%", 5.19), ("%", 8.39), ("%", 8.59), ("%", 10.49), ("", 27.0), ("", 28.0), ("", 2026.0)})
    text = render(AnswerPlan("change", facts, permitted, (), True, None, flat.source.snapshot_id)).text
    assert text.splitlines() == ["Between August 27, 2026 and September 28, 2026:",
                                 "48 Month Auto Loan, 2023-2026 model years: it was 4.99% APR.",
                                 "48 Month Auto Loan, 2016 and older model years: it was 8.39% APR; it is 8.59% APR.",
                                 "36 Month Personal Loan: unchanged at 10.49% APR.",
                                 "48 Month Auto Loan, 2024-2027 model years: it is 5.19% APR."]
    per_row = ("48 Month Auto Loan, 2023-2026 model years: on August 27, 2026 it was 4.99% APR. 48 Month Auto Loan, 2016 and older"
               " model years: on August 27, 2026 it was 8.39% APR; on September 28, 2026 it is 8.59% APR. 36 Month Personal Loan:"
               " unchanged at 10.49% APR between August 27, 2026 and September 28, 2026. 48 Month Auto Loan, 2024-2027 model years:"
               " on September 28, 2026 it is 5.19% APR.")  # the rendering before the header: same numbers, longer text
    assert _numbers(text) == _numbers(per_row) and len(text) < len(per_row)

def test_as_of_prefix_and_earliest_crawl_note(store_full):
    dated = _plan(store_full, "What was the rate on the 10-month fixed jumbo special certificate as of May 2026?", "2026-05-31")
    assert (dated.as_of, dated.snapshot_id) == ("2026-05-31", "02_2026-05-19_recrawl")  # the question's 2026 is permitted
    assert render(dated).text == "As of May 2026, 10 Month Fixed Jumbo Certificate Special: 3.90% APY."
    assert render(replace(dated, as_of=None)).text == "10 Month Fixed Jumbo Certificate Special: 3.90% APY."
    assert not render(replace(dated, permitted_values=frozenset({("%", 3.9)}))).text.startswith("As of")  # no unpermitted year
    y = _plan(store_full, "Is the highest Share Savings APY 0.35%?")
    late = replace(y, as_of="2026-09-30", permitted_values=y.permitted_values | {("", 2026.0)})
    assert render(late).text == "No. As of September 2026, Share Savings, $25,000 or more: 0.20% APY."
    note = render(_plan(store_full, "What is the APY on the 10-month certificate special?", "2026-01-15")).conflict_note
    assert note == EARLIEST_NOTE == "Answered from the earliest website crawl available."

def test_as_of_prefix_only_for_a_month_the_crawl_covers(store_full):
    f = make_fact("cert_special", "apy", "3.90%", term_months=10, special=True)  # read on 05_2026-09-28_latest
    years = frozenset({("%", 3.9), ("", 2026.0), ("", 2027.0)})
    plan = replace(single_plan("value", f, years), as_of="2026-09-15")
    bare = "10 Month Fixed Certificate Special: 3.90% APY."
    assert render(plan).text == "As of September 2026, " + bare  # inside the crawl range
    assert render(replace(plan, as_of="2026-09-30")).text == "As of September 2026, " + bare  # the crawl's own month
    for after in ("2026-10-01", "2027-03-01"):  # after the last crawl: its facts are not dated to a later month
        assert render(replace(plan, as_of=after)).text == bare, after
    early = render(replace(plan, as_of="2026-01-15", first_crawl="2026-05-12", conflict_note=EARLIEST_NOTE))  # before the first crawl
    assert (early.text, early.conflict_note) == (bare + "\n" + EARLIEST_NOTE, EARLIEST_NOTE)
    assert render(replace(plan, snapshot_id=None)).text == bare  # no crawl date to bound the month
    assert render(replace(single_plan("yes_no", f, years), as_of="2027-03-01")).text == "Yes. " + bare  # guard before the verdict split
    pre = _answer(store_full, "What is the APY on the 10-month certificate special?", "2026-01-15")  # real store, both ends
    assert (pre.text, pre.conflict_note) == ("10 Month Fixed Certificate Special: 3.80% APY.\n" + EARLIEST_NOTE, EARLIEST_NOTE)
    post = _answer(store_full, "What is the APY on the 10-month certificate special?", "2027-03-01")
    assert (post.text, post.conflict_note) == ("10 Month Fixed Certificate Special: 3.90% APY.", None)

def test_strip_residue_and_lint_split_lines():
    assert strip_residue("**Routing Number:** 273974581\\r\\n4.10%2 APY \\*") == "Routing Number: 273974581 4.10% APY"
    text = "Share Savings: 0.20% APY.\nBright Savings: 2.25% APY.\nFree Checking: 3% APY."
    assert lint(text, frozenset({("%", 0.2), ("%", 2.25)})) == ("Share Savings: 0.20% APY.\nBright Savings: 2.25% APY.", ["Free Checking: 3% APY."])

def test_label_words_and_a_lint_emptied_plan_refuses():
    names = product_names()
    assert label(make_fact("cert_special", "apy", "4.20%", term_months=17, special=True, jumbo=True), names) == "17 Month Fixed Jumbo Certificate Special"
    assert label(make_fact("auto_loan", "apr", "8.59% APR", term_months=48, model_year_min=0, model_year_max=2016), names) == "48 Month Auto Loan, 2016 and older model years"
    a = render(single_plan("value", make_fact("share_savings", "apy", "0.35%"), frozenset({("%", 0.2)})))
    assert a.confident is False and a.text == refusal("that").text and a.sources == []

def test_hours_without_a_branch_end_with_the_branch_note():
    a = render(single_plan("hours", make_fact("branch", "lobby_hours", "Monday–Friday, 8:30 a.m.–5 p.m.")))
    assert a.text == "Lobby hours: Monday–Friday, 8:30 a.m.–5 p.m.\nHours vary by branch; tell me which branch and I'll confirm."

def test_past_template_dates_the_old_side_or_says_unchanged():  # review round item 1 (C1): plan intent "past"
    def at(f, sid): return replace(f, source=replace(f.source, snapshot_id=sid))
    old = at(make_fact("cert_special", "apy", "3.95%", term_months=17, special=True), "04_2026-08-27_rebaseline")
    first = at(make_fact("personal_loan", "apr", "10.49%", term_months=36), "01_2026-05-12_baseline")
    now = make_fact("personal_loan", "apr", "10.49%", term_months=36)  # the reference crawl (plan.snapshot_id) has the row
    permitted = frozenset({("%", 3.95), ("%", 10.49), ("", 12.0), ("", 27.0), ("", 2026.0)})
    plan = AnswerPlan("past", (old, first, now), permitted, (), True, None, now.source.snapshot_id)
    lines = "17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026.\n36 Month Personal Loan: unchanged at 10.49% APR since May 12, 2026."
    assert render(plan).text == lines and render(replace(plan, as_of="2026-09-15")).text == lines  # no "As of" prefix
    bare = render(replace(plan, permitted_values=frozenset({("%", 3.95), ("%", 10.49)}))).text  # no date permitted
    assert bare == "17 Month Fixed Certificate Special: 3.95% APY in an earlier crawl.\n36 Month Personal Loan: unchanged at 10.49% APR."

def test_url_how_to_status_and_count_templates():
    link = make_fact("cert_regular", "url", "https://www.dupaco.com/rates")
    a = render(single_plan("url", link))
    assert (a.text, [s.url for s in a.sources]) == ("Regular Certificates: https://www.dupaco.com/rates", ["https://www.dupaco.com/rates"])
    join, minimum = make_fact("membership", "url", "https://join.dupaco.com/"), make_fact("share_savings", "min_to_open", "$5")
    how = AnswerPlan("how_to", (join, minimum), frozenset({("$", 5.0)}), (join.source,), True, None, join.source.snapshot_id)
    assert render(how).text == "You can do that online at https://join.dupaco.com/\nShare Savings: $5 minimum to open."
    closing = make_fact("branch", "status", "Closing November 14, 2026", branch_name="hy-vee")
    assert render(single_plan("status", closing)).text == "Hy-Vee Branch: Closing November 14, 2026."
    assert render(single_plan("count", make_fact("branch_count", "count", "18"))).text == "Branch Count: 18."
