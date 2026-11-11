# Phase 2 gate review round (Task 14), resolver pins: past values (C1), jumbo by amount (I3), hard qualifiers (I8),
# refusal spans (item 4, W1), unlisted branches (W5), unpriced programs and unanswerable attributes.
# Moved out of tests/test_20_resolve.py so both files stay under 500 lines; the shared helpers stay there.
import dataclasses
import datetime

from kb import tiers
from kb.compose import render
from kb.question import Query, parse
from kb.resolve import resolve, select_tier
from kb.store import FactStore
from kb.types import ClaimType, Fact, Source, make_key
from scoring import REFUSAL_RE
from test_20_resolve import R, _ask, _plan, _tier, _values

# review round item 1 (C1): a past-value question (Query.past, the parser's explicit cues) answers the old side only:
# the most recent earlier crawl whose value differs, dated; today's value (the trap) never appears.
from scoring import contains

@dataclasses.dataclass(frozen=True)
class _Past(Query):  # Query.past lands with the parser branch; the shim runs these pins before and after the merge
    past: bool = False

def _past(question, as_of=None): return _Past(**{**vars(parse(question, as_of, R)), "past": True})

def test_past_value_answers_the_old_side_only(store_full):
    seventeen = "What was the previous rate on the 17-month special certificate?"  # 3.85% (03) -> 3.95% (04) -> 4.10% (05)
    p = resolve(_past(seventeen), store_full, R)
    assert p.intent == "past" and render(p).text == "17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026."
    assert {("%", 3.95), ("", 27.0), ("", 2026.0)} <= p.permitted_values and ("%", 4.10) not in p.permitted_values
    dated = resolve(_past(seventeen, "2026-09-01"), store_full, R)  # the reference crawl is 04, so its 3.95% is the trap
    assert render(dated).text == "17 Month Fixed Certificate Special: 3.85% APY as of June 9, 2026."
    assert ("%", 3.95) not in dated.permitted_values and {("", 9.0), ("", 2026.0)} <= dated.permitted_values
    jumbo = render(resolve(_past("What was the previous rate on the 10-month fixed jumbo special certificate?"), store_full, R)).text
    assert contains(jumbo, "3.90%") and not contains(jumbo, "4.00%"), jumbo  # dup-006's must_not_include
    real = parse(seventeen, None, R)  # end to end with the merged parser: "previous" is an explicit past cue
    assert real.past and resolve(real, store_full, R).intent == "past"
    plain = "What is the rate on the 17-month special certificate?"  # no past cue: answered as before
    assert not parse(plain, None, R).past and resolve(parse(plain, None, R), store_full, R).intent == "value"

def test_past_value_unchanged_absent_and_change_wording(store_full):
    flat = resolve(_past("What was the previous APR on a 36-month personal loan?"), store_full, R)  # 10.49% in every crawl
    assert render(flat).text == "36 Month Personal Loan: unchanged at 10.49% APR since May 12, 2026."
    gone = "What was the previous APY on the 25-month certificate special?"  # crawls 01-02 only
    assert resolve(_past(gone), store_full, R).confident is False  # absent at the reference crawl: refused
    assert resolve(_past(gone, "2026-05-15"), store_full, R).confident is False  # fix round 2: its reference crawl is the first
    before = resolve(_past("What was the 17-month special certificate rate before it changed?"), store_full, R)  # change wording
    assert before.intent == "past" and render(before).text == "17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026."
    mortgage = resolve(_past("What was the previous 30-year fixed mortgage rate for loans of $100,000 or less?"), store_full, R)
    assert render(mortgage).text == "30-Year Fixed Home Loans - Purchase, $100,000 or less: 6.375% rate (6.514% APR) as of August 27, 2026."
    assert not {("%", 7.13), ("%", 7.27)} & mortgage.permitted_values  # today's rate and its APR stay out

# fix round 2 (C1, relabelled tiers): crawl 05 relabelled every auto tier (2023-2026 -> 2024-2027, 2021-2022 -> 2021-2023),
# so no earlier crawl has today's key; the walk pairs that crawl's tier of the same other qualifiers with the largest
# model-year overlap. A row no earlier crawl dates is dropped, never "unchanged ... since" its own reference crawl (refused
# when none is left); a relabelled tier left unchanged dates nothing, since its old key would print apart from today's.
def test_past_value_pairs_a_relabelled_model_year_tier(store_full):
    one = render(_plan(store_full, "What was the previous APR on a 60-month auto loan for a 2025 model year?")).text
    assert one == "60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026." and not contains(one, "5.39%")
    up = render(_plan(store_full, "What was the APR of the 60-month auto loan before it went up?")).text
    assert up.splitlines() == ["60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026.",
                               "60 Month Auto Loan, 2021-2022 model years: 5.44% APR as of August 27, 2026.",
                               "60 Month Auto Loan, 2017-2020 model years: 6.14% APR as of August 27, 2026."]
    old = render(_plan(store_full, "What was the 84-month auto loan APR for a 2024 vehicle before it changed?")).text
    assert old == "84 Month Auto Loan, 2023-2026 model years: 5.39% APR as of August 27, 2026." and "unchanged" not in old

def test_no_past_plan_dates_a_row_to_its_reference_crawl(store_full):
    crawls = store_full.snapshots()
    for pid in sorted(set(R.aliases().values())):  # every product, published attribute and reference crawl
        for attribute in sorted(R.published(pid)):
            for as_of, day in [(day, day) for _, day in crawls] + [(None, crawls[-1][1])]:
                q = Query("value", pid, attribute, (), as_of, False, "", frozenset(), "", (pid,), past=True)
                d = datetime.date.fromisoformat(day)
                text = render(resolve(q, store_full, R)).text
                assert "since {:%B} {}, {}".format(d, d.day, d.year) not in text, (pid, attribute, as_of, text)

def _auto(sid, years, value):  # one 60-month auto APR row of a synthetic crawl
    key = make_key("auto_loan", "apr", {"model_year_min": years[0], "model_year_max": years[1], "term_months": 60})
    src = Source("https://www.dupaco.com/rates", "https://www.dupaco.com/rates", "rate_sheet", 3, sid, sid[3:13], 0, 0, "row")
    return Fact(key, "auto_loan", "apr", key[2], value, "{}% APR".format(value), "pct", ClaimType.RATE, None, None, None, src, "rules", 1.0)

def test_a_relabelled_tier_left_unchanged_dates_nothing():
    def store(*crawls):
        s = FactStore()
        for sid, years, value in crawls:
            s.add(sid, sid[3:13], [_auto(sid, years, value)])
        s.finalize(); return s
    may, june = ("01_2026-05-12_baseline", (2023, 2026), 4.99), ("03_2026-06-09_recrawl", (2023, 2026), 5.19)
    sept = ("05_2026-09-28_latest", (2024, 2027), 5.19)  # relabelled, the value unchanged since June
    question = _past("What was the previous APR on a 60-month auto loan?")
    assert render(resolve(question, store(may, june, sept), R)).text == "60 Month Auto Loan, 2023-2026 model years: 4.99% APR as of May 12, 2026."
    assert resolve(question, store(june, sept), R).confident is False  # no earlier crawl differs: no row is left

# review round item 2 (I3): an amount at or above a jumbo row's minimum to earn (read from the min_to_earn rows) selects
# that jumbo row; a row family without a jumbo row, and an amount below every minimum, answer as before
def test_amount_at_a_jumbo_minimum_selects_the_jumbo_row(store_full):
    assert _values(_plan(store_full, "What is the 17-month special certificate rate for $100,000 or more?")) == [4.20]
    assert _values(_plan(store_full, "10 month special with $150,000")) == [4.00]
    assert _values(_plan(store_full, "What is the APY on the 17-month CD for $100,000?")) == [4.20]  # via the special sibling
    assert _values(_plan(store_full, "What is the rate on $5,000 in the 17-month special?")) == [4.10]  # below: the regular row
    assert _values(_plan(store_full, "What special certificate rates can I get with $150,000?")) == [4.00, 4.20]
    ira = _plan(store_full, "What are the IRA certificate rates for $150,000?")
    specials = [f for f in ira.facts if dict(f.qualifiers)["special"]]
    assert specials and all(dict(f.qualifiers)["jumbo"] for f in specials) and len(ira.facts) - len(specials) == 6  # 3 terms x 2

def test_jumbo_minimums_prefer_per_row_family():
    rows = [_tier(4.10, special=True, term_months=17, jumbo=False), _tier(4.20, special=True, term_months=17, jumbo=True), _tier(2.70, term_months=18)]
    floor = {rows[1].qualifiers: 100000.0}
    assert [f.value for f in select_tier(rows, _ask(amount=100000.0), floor)] == [2.70, 4.20]  # the minimum is inclusive
    assert [f.value for f in select_tier(rows, _ask(amount=99999.99), floor)] == [2.70, 4.10, 4.20]  # below it: as before
    assert [f.value for f in select_tier(rows, _ask(amount=150000.0, jumbo=False), floor)] == [2.70, 4.10]  # an asked jumbo rules
    assert [f.value for f in select_tier(rows, _ask(amount=150000.0))] == [2.70, 4.10, 4.20]  # no minimums: as before

# re-review #2: an upper bound ("up to $100,000", "$100,000 or less") reaches no jumbo minimum, so the regular row
# answers, and it stays in the loan-amount tier that ends at it
def test_an_upper_bound_amount_selects_no_jumbo_row(store_full):
    phrases = ("up to $100,000", "$100,000 or less", "under $100,000", "less than $100,000", "$100,000 and under")
    got = {p: _values(_plan(store_full, "What is the 17-month special certificate rate for %s?" % p)) for p in phrases}
    assert got == {p: [4.10] for p in phrases}
    assert _values(_plan(store_full, "What is the 30-year fixed mortgage rate for a loan of $100,000 or less?")) == [7.13, 7.27]  # rate, APR

# review round item 3 (I8): a qualifier the product does not offer refuses instead of being dropped
def _with_slots(q, **extra): return dataclasses.replace(q, slots=tuple(sorted({**dict(q.slots), **extra}.items(), key=lambda kv: kv[0])))

def test_jumbo_is_a_hard_qualifier(store_full):
    mortgage = _with_slots(parse("What is the rate on a jumbo mortgage?", None, R), jumbo=True)  # the parser's jumbo slot
    assert resolve(mortgage, store_full, R).confident is False  # no mortgage row is jumbo
    assert _values(_plan(store_full, "What is the APY on the 10-month jumbo certificate special?")) == [4.00]
    assert _values(_plan(store_full, "As of August 31, 2026, what APY did the 17-month jumbo certificate special pay?", "2026-08-31")) == [4.05]
    plain = [_tier(7.13, term_months=360), _tier(6.75, term_months=180)]  # rows without the flag read as not jumbo
    assert select_tier(plain, _ask(jumbo=True)) == [] and tiers.misses(_ask(jumbo=True), plain)
    assert [f.value for f in select_tier(plain, _ask(jumbo=False))] == [6.75, 7.13]

def test_jumbo_passes_product_level_facts(store_full):  # a link or description carries no tier, so jumbo cannot miss it
    for question, url in (("What's the link for the jumbo certificate special?", "https://www.dupaco.com/personal/savings-account"),
                          ("What is the URL for the IRA jumbo special certificate?", "https://www.dupaco.com/personal/retirement"),
                          ("Where can I find the jumbo certificate special online?", "https://www.dupaco.com/personal/savings-account")):
        assert [f.value_text for f in _plan(store_full, question).facts] == [url], question
    assert [f.value for f in select_tier([_tier(1.0)], _ask(jumbo=True))] == [1.0]  # no qualifier at all: not a tier
    assert tiers.misses(_ask(jumbo=True), [_tier(7.13, term_months=360)])  # tiered rows without a jumbo tier still miss

def _hours_store():
    key = make_key("branch", "lobby_hours", {})
    src = Source("https://www.dupaco.com/locations", "https://www.dupaco.com/locations", "locations", 3, "s", "2026-09-28", 0, 0, "row")
    s = FactStore()
    s.add("s", "2026-09-28", [Fact(key, "branch", "lobby_hours", (), None, "Monday-Friday 9 a.m.-5 p.m.", "text", ClaimType.ASSERTION,
                                   None, None, None, src, "rules", 1.0)])
    s.finalize(); return s

def test_a_segment_the_family_does_not_offer_refuses(store_full):
    for question in ("What is the APR on a business HELOC?", "What is the APR on a business auto loan?", "What is the rate on a commercial mortgage?"):
        p = _plan(store_full, question)  # home equity, auto and mortgage are personal-only, and no business sibling has the attribute
        assert p.confident is False and not p.facts, question
    for question in ("What is the APY on business checking?", "What is the APY on business savings?", "What is the APR on the business Platinum Visa?",
                     "What are the APRs on the auto loan and the business Platinum Visa?",  # a business product is named
                     "What is the routing number for business accounts?", "What is the phone number for business services?",
                     "What is the address of the Galena branch for business members?"):  # branch and membership facts serve both
        assert _plan(store_full, question).confident, question
    assert _plan(_hours_store(), "What are your business hours?").confident  # "business hours" asks the branch hours

# review round item 4 and W1: a refusal restates no unrecognised product name and no number, URL or domain from the
# question (a should_refuse item's must_not_include may list any of them); a recognised product's plain span stays
def test_refusal_span_restates_no_unknown_name_number_or_link(store_full):
    jump = render(_plan(store_full, "What is the APY on the Jump Start savings account?"))  # dev-017: no product recognised
    assert jump.confident is False and REFUSAL_RE.search(jump.text) and "Jump Start" not in jump.text
    for question, trap in (("Is Jump Start savings still paying 2.25%?", "2.25%"), ("Is the 25-month certificate special still available at 3.60%?", "3.60%"),
                           ("Is the 7/1 ARM rate still 6.037%?", "6.037%"),
                           ("What's the 25-month special APY now that it's no longer 3.60%?", "3.60%"),
                           ("What is your rate on a 7/1 adjustable-rate mortgage?", "7/1")):
        a = render(_plan(store_full, question))
        assert a.confident is False and REFUSAL_RE.search(a.text), question
        if "no longer offered" in a.text:  # A14b allows only product-label numbers already in the question
            from kb.normalize import number_tokens
            assert number_tokens(a.text) <= number_tokens(question), (question, a.text)
        else:
            assert not any(ch.isdigit() for ch in a.text), (question, a.text)
        assert not contains(a.text, trap), (question, a.text)
    for question in ("What interest rate does dupaco.com list for a construction loan?",
                     "What interest rate does https://www.dupaco.com/loans list for a construction loan?"):
        p = _plan(store_full, question)
        assert p.confident is False and parse(question, None, R).product_id == "construction_loan" and p.refusal_span == "that", question
    assert _plan(store_full, "What interest rate do you charge on a construction loan?").refusal_span == "the interest rate on a construction loan"
    assert _plan(store_full, "Can you give me the lobby hours for the Mullan Avenue branch?").refusal_span == "the lobby hours for the Mullan Avenue branch"

# review round W5: a phone, address or hours question naming a branch no branch fact carries (the contact page lists
# six by address; the hours articles' branches count for hours questions only) refuses instead of answering with the
# membership number; branch_name stays soft for rate questions
def test_contact_questions_naming_an_unlisted_branch_refuse(store_full):
    for question in ("What is the phone number of the Mullan Avenue branch?", "What is the phone number at the Hy-Vee branch?",
                     "What is the address of the Mullan Avenue branch?", "Can you give me the lobby hours for the Mullan Avenue branch?"):
        p = _plan(store_full, question)
        assert p.confident is False and not p.facts, question
    slotted = _with_slots(parse("What is Dupaco's phone number?", None, R), branch_name="mullan avenue")  # a parser that sets the slot
    assert resolve(slotted, store_full, R).confident is False
    for question in ("What is Dupaco's phone number?", "What is the phone number of the Galena branch?",  # no branch, a listed one
                     "What number do I call to reach a branch location?", "What is the phone number for branch services?"):
        assert [f.value_text for f in _plan(store_full, question).facts] == ["800-373-7600"], question
    assert [f.value_text for f in _plan(store_full, "What is the address of the Galena Branch?").facts] == ["11375 Oldenburg Ln., Galena, IL, 61036"]
    for question in ("What is the savings rate at the Galena branch?", "What is the savings rate at the Mullan Avenue branch?"):
        assert _plan(store_full, question).confident, question  # a rate question: the branch name narrows nothing

# lane H fix round (I1): the newsroom hours articles name branches the contact page does not list (Platteville, Grimes,
# Cedar Rapids, Waukee, the two Madison branches); their hours facts list a branch for an hours question only
def test_hours_articles_list_branches_for_hours_questions_only(store_full):
    for question in ("What is the phone number for the Platteville branch?", "What is the phone number of the Grimes branch?",
                     "What is the phone number for the Cedar Rapids branch?", "What is the phone number for the East Washington branch?"):
        p = _plan(store_full, question)
        assert p.confident and p.facts and all(f.product_id == "branch" and f.attribute == "phone" for f in p.facts), question  # A11b: published article phones
    for question in ("What are the lobby hours at the Platteville branch?", "What are the drive-up hours at the Platteville branch?"):
        p = _plan(store_full, question)  # both hours arms (Task 11 review)
        assert p.confident and {dict(f.qualifiers)["branch_name"] for f in p.facts} == {"platteville"}, question

# review round: the parser branch reads unpriced mortgage programs (VA, FHA, USDA, interest-only, investment ...) as
# program values no fact carries, and unanswerable attribute words (penalty, compounding, closing costs ...) as an
# attribute no fact carries; the arbitration refuses both, digit-free
def test_unpriced_programs_and_unanswerable_attributes_refuse(store_full):
    for question, program in (("What is the 30-year VA mortgage rate?", "va"), ("What is the FHA refinance rate?", "fha"),
                              ("What is the 15-year USDA mortgage APR?", "usda"), ("What is the interest-only mortgage rate?", "interest_only"),
                              ("What is the cash-out refinance rate for an investment property?", "investment")):
        q = _with_slots(parse(question, None, R), program=program)
        a = render(resolve(q, store_full, R))
        assert a.confident is False and REFUSAL_RE.search(a.text) and not any(ch.isdigit() for ch in a.text), question
    for question, attribute in (("What is the early withdrawal penalty on the 17-month certificate special?", "penalty"),
                                ("How often are dividends compounded on Share Savings?", "compounding"),
                                ("What are the closing costs on a 30-year mortgage?", "closing_costs")):
        q = dataclasses.replace(parse(question, None, R), attribute=attribute)
        a = render(resolve(q, store_full, R))
        assert attribute not in R.published(q.product_id) and a.confident is False and not any(ch.isdigit() for ch in a.text), question

# fix round 3, F1: "previous to" is a past cue again (only "prior to" is not), so the old value prints, as at base
def test_previous_to_answers_the_old_value(store_full):
    got = [render(_plan(store_full, q)).text for q in ("What was the 17-month special APY previous to the latest update?",
                                                       "What was the 17-month special APY previous to September?",
                                                       "What was the 10-month jumbo special APY previous to the last update?")]
    assert got == ["17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026."] * 2 + [
        "10 Month Fixed Jumbo Certificate Special: 3.90% APY as of August 27, 2026."]

# fix round 3, F2: a negated lower bound reaches the jumbo minimum, or the balance tier it opens, as at base; the added
# upper bounds select the regular row
def test_negated_lower_bounds_and_more_upper_bounds_select_their_rows(store_full):
    assert _values(_plan(store_full, "What is the 17-month special certificate rate for less than $100,000?")) == [4.10]  # as before
    lower = {"What is the 17-month special certificate rate for no less than $100,000?": [4.20],
             "What does Share Savings pay on balances of not less than $25,000?": [0.20],
             "What does 1st Rate Checking pay on balances of no less than $5,000?": [2.50],
             "What does the money market pay on no less than $100,000?": [0.40]}
    upper = ("at most", "no more than", "not more than", "a maximum of", "max", "no greater than", "not exceeding", "a deposit capped at")
    got = {q: _values(_plan(store_full, q)) for q in list(lower) + ["What is the 17-month special certificate rate for %s $100,000?" % p
                                                                    for p in upper]}
    assert got == {**lower, **{"What is the 17-month special certificate rate for %s $100,000?" % p: [4.10] for p in upper}}

# fix round 3, F3: a site word before a verb names the source, so the value answers; a bare "on site" is no website
def test_a_site_word_before_a_verb_answers_the_value(store_full):
    assert render(_plan(store_full, "What is the website showing for the HELOC APR?")).text == "Home Equity Line of Credit: 6.25% APR."
    assert render(_plan(store_full, "Where is the ATM on site at the Key West branch?")).confident is False  # as at base

# fix round 3, F4: "where on the website's ... page" answers the url again, as at base, and so does "where's"
def test_where_on_a_possessive_site_word_answers_the_url(store_full):
    got = {q: render(_plan(store_full, q)).text for q in ("Where on the website's contact page is the branch and ATM locator?",
                                                          "Where on the website's membership page can I join online?")}
    assert got == {"Where on the website's contact page is the branch and ATM locator?": "Branch: https://www.dupaco.com/contact",
                   "Where on the website's membership page can I join online?": "Membership: https://join.dupaco.com/"}
    savings = render(_plan(store_full, "Where on the website's savings page are the certificate rates?")).text
    heloc = render(_plan(store_full, "Where's the HELOC APR on the website?")).text
    assert contains(savings, "dupaco.com/personal/savings-account") and contains(heloc, "dupaco.com/personal/loans/home-equity")

# fix round 3, F5: an asked model year pairs with the earlier crawl's tier that contains it (in August a 2023 car sat in
# 2023-2026, not 2021-2022); with no year asked, the largest overlap as before (test_past_value_pairs_a_relabelled_
# model_year_tier); 2027 sat in no earlier tier, so it refuses (accepted)
def test_past_value_pairs_the_tier_containing_the_asked_model_year(store_full):
    got = [render(_plan(store_full, q)).text for q in ("What was the previous APR on a 60-month auto loan for a 2023 model year?",
                                                       "What was the previous APR on a 72-month auto loan for a 2023 model year?",
                                                       "What was the previous APR on an 84-month auto loan for a 2023 model year?")]
    assert got == ["60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026.",
                   "72 Month Auto Loan, 2023-2026 model years: 5.29% APR as of August 27, 2026.",
                   "84 Month Auto Loan, 2023-2026 model years: 5.39% APR as of August 27, 2026."]
    assert render(_plan(store_full, "What was the previous 48-month auto loan APR for a 2027 model year?")).confident is False

# fix round 3, F6: a current auto question with an incidental past word answers today's rows, undated
def test_incidental_past_words_answer_todays_rows(store_full):
    p = _plan(store_full, "What's the current 60-month auto loan rate for a previously leased car?")
    assert (p.intent, _values(p)) == ("value", [5.39, 5.64, 6.34])

# fix round 4, N1: the paraphrases of the weight-1.5 url items answer their urls again, as at 7ff32f7; the F3 value
# questions keep their values
def test_more_ways_of_asking_for_the_website_answer_their_urls(store_full):
    contact, join = "Branch: https://www.dupaco.com/contact", "Membership: https://join.dupaco.com/"
    savings = "Regular Certificates: https://www.dupaco.com/personal/savings-account"
    want = {"Which website offers the branch and ATM locator?": contact, "What website gives Dupaco's CD rates?": savings,
            "Which site lets me join online?": join, "What website is used to join Dupaco online?": join,
            "What's the website with the branch locator?": contact, "What is the website with the CD rates?": savings,
            "Which website contains certificate rates?": savings, "What site is the ATM locator on?": contact,
            "What website am I supposed to use to join?": join, "What's the website called where I can join?": join,
            "What's the website I'd use to join?": join, "What's the website you'd recommend for CD rates?": savings,
            "What is the website showing for the HELOC APR?": "Home Equity Line of Credit: 6.25% APR.",
            "What's the website offering on the 17-month special certificate?": "17 Month Fixed Certificate Special: 4.10% APY.",
            "What's the website saying the HELOC APR is?": "Home Equity Line of Credit: 6.25% APR."}
    assert {q: render(_plan(store_full, q)).text for q in want} == want

# fix round 4, N2: a past question naming a model-year range pairs the earlier tier sharing the most of its years (in
# August 2024-2027 was 2023-2026; 2021-2023 shares two years with 2021-2022, one with 2023-2026); a single year keeps the
# tier containing it, so 2027 still refuses; a current question with a range answers today's tier, as before
def test_past_value_pairs_the_tier_sharing_most_of_an_asked_range(store_full):
    got = [render(_plan(store_full, "What was the previous %d-month auto loan APR for the 2024-2027 model years?" % n)).text
           for n in (60, 72, 84)]
    assert got == ["60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026.",
                   "72 Month Auto Loan, 2023-2026 model years: 5.29% APR as of August 27, 2026.",
                   "84 Month Auto Loan, 2023-2026 model years: 5.39% APR as of August 27, 2026."]
    assert render(_plan(store_full, "What was the previous APR on a 60-month auto loan for 2021-2023 model years?")).text == (
        "60 Month Auto Loan, 2021-2022 model years: 5.44% APR as of August 27, 2026.")
    assert render(_plan(store_full, "What was the previous 60-month auto loan APR for a 2027 model year?")).confident is False
    assert render(_plan(store_full, "What is the 60-month auto loan APR for the 2024-2027 model years?")).text == (
        "60 Month Auto Loan, 2024-2027 model years: 5.39% APR.")

# fix round 4, F6 leftover: a current question whose "was" sits in a later clause, or with "previously been ...",
# answers today's rows, undated; the past questions keep the old value
def test_a_later_was_or_previously_been_answers_todays_rows(store_full):
    current = ("What is the 60-month auto APR for a car that has previously been financed?",
               "What's the 60-month auto rate if the car was previously leased?",
               "What is the 60-month auto loan rate for a vehicle that was previously financed elsewhere?",
               "What is the 60-month auto APR if I was previously approved for a loan?",
               "What is the 60-month auto APR for a vehicle that has previously been titled in another state?",
               "What rate do you charge on a 60-month loan for a car that's previously been leased?")
    got = {q: (_plan(store_full, q).intent, _values(_plan(store_full, q))) for q in current}
    assert got == {q: ("value", [5.39, 5.64, 6.34]) for q in current}
    old = "17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026."
    assert [render(_plan(store_full, q)).text for q in ("What was the previous rate on the 17-month special?",
                                                        "What did the 17-month special pay before it changed?",
                                                        "What has the 17-month special previously been?")] == [old] * 3
    assert _plan(store_full, "Which certificate specials were previously offered?").intent == "past"  # corpus pc-22
    for q in ("What is the APY that was previously offered on the 17-month special?",  # follow-up: a "was" about the rate
              "What's the rate the 17-month special was previously offered at?"):
        assert render(_plan(store_full, q)).text == old, q

# fix round 4, N4: "in the previous year" asks one year before the as_of date (the newest crawl's when undated); a day
# before the first crawl (May 12, 2026) is refused, digit-free, and a later one is answered as of that day; a model-year
# "prior-year model" question still answers today's rows
def test_the_previous_year_refuses_before_the_first_crawl(store_full):
    asks = ("What was the 17-month special APY in the previous year?", "What did the 17-month special pay in the prior year?",
            "What was the APY on Share Savings the previous year?")
    for q, as_of in [(q, None) for q in asks] + [(asks[0], "2026-09-01")]:
        a = render(_plan(store_full, q, as_of))
        assert a.confident is False and REFUSAL_RE.search(a.text) and not any(ch.isdigit() for ch in a.text), (q, as_of, a.text)
    later = _plan(store_full, asks[0], "2027-06-30")  # one year back is June 30, 2026: crawl 03's 3.85%
    assert (later.as_of, _values(later)) == ("2026-06-30", [3.85])
    for q in ("What is the 60-month APR for a prior-year model car?", "What is the APR for a previous year's model on a 60-month auto loan?"):
        assert _values(_plan(store_full, q)) == [5.39, 5.64, 6.34], q

# fix round 4, N5: the added upper bounds select the regular 4.10% row on the 17-month special; "climax $100,000" reads
# as written and reaches the jumbo row
def test_more_upper_bounds_select_the_regular_row(store_full):
    upper = ["What is the 17-month special certificate rate %s $100,000?" % p for p in (
        "for a max of", "for maximum", "for not greater than", "not to exceed", "for up to and including", "for no higher than",
        "for not over")]
    assert {q: _values(_plan(store_full, q)) for q in upper} == {q: [4.10] for q in upper}
    assert _values(_plan(store_full, "What is the 17-month special certificate rate for climax $100,000?")) == [4.20]

# fix round 5, R1: the previously offered or advertised value prints the old value, never today's (the C1 trap)
def test_previously_before_a_rate_participle_answers_the_old_value(store_full):
    want = {"What is the previously offered APY on the 17-month special?": "17 Month Fixed Certificate Special: 3.95% APY as of August 27, 2026.",
            "What is the formerly offered APY on the 10-month jumbo special?":
                "10 Month Fixed Jumbo Certificate Special: 3.90% APY as of August 27, 2026.",
            "What is the previously advertised 60-month auto loan APR for a 2025 car?":
                "60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026."}
    assert {q: render(_plan(store_full, q)).text for q in want} == want

# fix round 5, D: a past question naming "between X and Y" model years pairs the earlier tier sharing the most of them,
# as "from X to Y" does; a current one answers today's tier, as before
def test_past_value_pairs_the_tier_sharing_most_of_a_between_range(store_full):
    want = {"What was the previous 60-month auto loan APR for between 2024 and 2027 model years?":
                "60 Month Auto Loan, 2023-2026 model years: 5.19% APR as of August 27, 2026.",
            "What was the previous 60-month auto loan APR for between 2021 and 2023 model years?":
                "60 Month Auto Loan, 2021-2022 model years: 5.44% APR as of August 27, 2026.",
            "What was the previous 60-month auto loan APR for from 2021 to 2023 model years?":
                "60 Month Auto Loan, 2021-2022 model years: 5.44% APR as of August 27, 2026.",
            "What is the 60-month auto loan APR for between 2021 and 2023 model years?": "60 Month Auto Loan, 2021-2023 model years: 5.64% APR."}
    assert {q: render(_plan(store_full, q)).text for q in want} == want
