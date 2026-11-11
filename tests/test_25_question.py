# tests/test_25_question.py
import json, time
from kb.question import parse
from kb.registry import Registry
R = Registry.load()

def test_public_slots_match_labels(public_items):
    labels = json.load(open("tests/fixtures/public_slots.json"))
    by_id = {it["id"]: it for it in public_items}
    for qid, want in labels.items():
        q = parse(by_id[qid]["question"], by_id[qid].get("as_of"), R)
        assert (q.product_id, q.attribute, q.intent) == (want["product_id"], want["attribute"], want["intent"]), qid
        for k, v in want.get("slots", {}).items(): assert dict(q.slots)[k] == v, (qid, k)

def test_argument_as_of_beats_question_date():
    q = parse("What was the 10-month jumbo special APY as of May 2026?", "2026-08-31", R)
    assert q.as_of == "2026-08-31"

def test_as_of_formats_resolve_to_same_snapshot():
    keys = {parse("What was the 10-month jumbo special APY?", a, R).as_of for a in ("2026-05-31", "05/31/2026", "2026-05", "May 2026")}
    assert keys == {"2026-05-31"}
    assert parse("x", "not-a-date", R).as_of_error is True

# Gate review I7: a YYYY-MM after a date word is the month's last day, like the argument; model years or $ spans are not.
def test_question_year_month_is_the_month_end_like_the_argument():
    q = parse("What was the 10-month jumbo special APY as of 2026-05?", None, R)
    assert (q.as_of, q.as_of_error) == ("2026-05-31", False)
    assert q.canonical_key == parse("What was the 10-month jumbo special APY?", "2026-05", R).canonical_key
    assert parse("What was the Share Savings APY in 2026-06?", None, R).as_of == "2026-06-30"
    assert [parse(q, None, R).as_of for q in ("What is the 60-month auto loan APR for a 2010-11 model year?",
                                               "Share Savings APY between $2000-12,000")] == [None, None]

def test_canonical_key_ignores_punctuation_variants():
    a = parse("What's the APY on the 17-month special certificate?", None, R)
    b = parse("What is the apy on the 17 month special certificate", None, R)
    c = parse("What’s the yield on the 17–month special CD?", None, R)
    assert a.canonical_key == b.canonical_key == c.canonical_key

def test_input_cap_and_fuzz():
    t = time.perf_counter(); q = parse("9" * 100_000 + " rate?", None, R)
    assert len(q.raw_span) <= 1000 and time.perf_counter() - t < 1.0
    assert parse(None, None, R).intent == "value" and parse(42, None, R).raw_span == ""

# Fix round 1 (review of 2d0ebf4): plan Review Focus 3 and 4 pins, alias tails, the N-year fixed default.
def test_alias_tail_words_stay_attributes():
    for question, want in (("What are the auto loan rates?", ("auto_loan", "apr")),
                           ("What is the membership eligibility?", ("membership", "eligibility")),
                           ("What is the member eligibility?", ("membership", "eligibility"))):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute) == want, question

# Gate review C1(a): a month written without a year takes the reference date's year (the facade passes the newest crawl's
# day), a later month too (the near future; integration ruling 6); no reference keeps the month dropped.
REF = "2026-09-28"

def test_a_month_without_a_year_takes_the_reference_year():
    for phrase, want in (("in May", "2026-05-31"), ("since June", "2026-06-30"), ("on May 31", "2026-05-31"),
                         ("in mid-May", "2026-05-15"), ("in September", "2026-09-30"), ("in October", "2026-10-31"),
                         ("on October 3", "2026-10-03")):
        question = "What was the 10-month fixed jumbo special certificate rate " + phrase + "?"
        assert (parse(question, None, R, reference_date=REF).as_of, parse(question, None, R).as_of) == (want, None), phrase
    assert parse("Is the Hy-Vee branch still open in October?", None, R, reference_date=REF).as_of == "2026-10-31"
    assert parse("Was the 60-month auto loan APR different in May?", None, R, reference_date=REF).intent == "change"
    for question in ("What is the Share Savings APY, and may I open it online?", "What was the APY on Share Savings?",
                     "Is the rate fixed or may it change?"):
        assert parse(question, None, R, reference_date=REF) == parse(question, None, R), question  # no month, no change
    assert [parse("What was the APY in May?", None, R, reference_date=ref).as_of for ref in ("not-a-date", "", None, 20260928)] == [None] * 4
    assert parse("What was the APY in May?", "2026-08-31", R, reference_date=REF).as_of == "2026-08-31"  # argument wins

# Gate review C1(b)(c), the resolver contract: Query.past only on explicit past wording, never a bare "was"; "before it
# changed" is no change cue; a change question keeps past False. Ruling 5 (SE6): a passive "used to <verb>" is no past
# cue and asks a purpose, never the rate; "used to be" and a "used to" inside a "that"/"it" clause stay past.
def test_past_wording_sets_past():
    q = parse("What was the previous rate on the 10-month fixed jumbo special certificate?", None, R, reference_date=REF)
    assert (q.past, q.as_of, q.product_id, q.attribute) == (True, None, "cert_special", "apy")
    q = parse("What did the 17-month special certificate pay before it changed?", None, R, reference_date=REF)
    assert (q.past, q.intent, q.product_id, q.attribute) == (True, "value", "cert_special", "apy")
    for question in ("What used to be the APY on the 17-month special?", "What was the prior APY on Share Savings?",
                     "What was the Share Savings APY formerly?", "What was the old APY on Share Savings?",
                     "What was the Share Savings APY before the change?", "What was the APY before the last change?",
                     "What was the 17-month special APY prior to the change?", "What did Share Savings pay previously?",
                     "What was the APY before the rate went up?", "Share Savings APY before the last rate change",
                     "What did the 60-month auto loan used to charge?", "What was the rate that the 17-month special used to pay?"):
        q = parse(question, None, R, reference_date=REF)
        assert (q.past, q.intent, q.canonical_key.endswith("|past")) == (True, "value", True), question
    q = parse("What was the APY on Share Savings?", None, R, reference_date=REF)
    assert q.past is False and q.canonical_key == "value|share_savings|apy|[('segment', 'personal')]|None"
    for question in ("How old do I need to be to open Launchpad Savings?", "What is the APR for a 10 year old car?",
                     "Should I open a CD before the rate changes?", "What do I need prior to opening Share Savings?",
                     "Can I lock the rate before they change it?"):
        assert parse(question, None, R, reference_date=REF).past is False, question
    for question in ("What is the HSA used to pay for?", "What's the HSA used to pay for?", "Can the HSA be used to pay for glasses?"):
        q = parse(question, None, R, reference_date=REF)
        assert (q.past, q.product_id, q.attribute) == (False, "hsa", "description"), question
    q = parse("How much did the 17-month special APY change from the previous rate?", None, R, reference_date=REF)
    assert (q.intent, q.past) == ("change", False)

# The contract with the resolver: "jumbo" sets the jumbo slot for any product (a product without jumbo rows refuses).
def test_jumbo_is_a_slot_for_any_product():
    for question, pid in (("What is the rate on a jumbo mortgage?", "mortgage_purchase"), ("What is the 10-month jumbo special APY?",
                          "cert_special"), ("What is the APY on a jumbo Share Savings account?", "share_savings")):
        q = parse(question, None, R)
        assert (q.product_id, dict(q.slots).get("jumbo")) == (pid, True), question
    assert "jumbo" not in dict(parse("What is the 30-year fixed mortgage rate?", None, R).slots)

# Gate review I1 (Review Focus P2-2 wording first): "X and Y <head>" names both when both halves are product names.
def test_coordinated_names_share_their_head():
    for question in ("What are the APRs on the Platinum and Rewards Visa?", "What are the APRs on the Platinum and Rewards cards?",
                     "rates on the Platinum and Rewards Visa cards", "Is the APR lower on the Platinum or Rewards Visa?"):
        q = parse(question, None, R)
        assert (q.product_id, q.product_ids, q.attribute) == ("platinum_visa", ("platinum_visa", "rewards_visa"), "apr"), question
    for question, ids in (("What are the APRs on the boat and personal loans?", ("boat_rv_loan", "personal_loan")),
                          ("What are the APRs on car and boat loans?", ("auto_loan", "boat_rv_loan")),
                          ("What are the APRs on the Platinum Visa and the Rewards Visa?", ("platinum_visa", "rewards_visa")),
                          ("What rewards come with the Platinum Visa?", ("platinum_visa",)),
                          ("Compare Share Savings and Bright Savings", ("share_savings", "bright_savings"))):
        assert parse(question, None, R).product_ids == ids, question
    assert parse("Which is better, Platinum or Rewards?", None, R).product_ids == ()

# Gate review I2: "auto" is a weak auto-loan word (not "auto-pay"/"auto-renew"); an auto refinance is the auto loan.
def test_auto_is_a_weak_auto_loan_word():
    for question in ("What is the 60-month auto rate?", "What are Dupaco's auto rates?", "auto APR for 60 months on a 2025 model",
                     "Was the 60-month auto rate higher in May 2026?", "APR on an auto refinance", "What are the rates on autos?"):
        q = parse(question, None, R)
        assert (q.product_id, q.product_ids, q.attribute) == ("auto_loan", ("auto_loan",), "apr"), question
    q = parse("Was the 60-month auto rate higher in May 2026?", None, R)
    assert (q.intent, q.as_of, dict(q.slots)["term_months"]) == ("yes_no", "2026-05-31", 60)
    assert dict(parse("auto APR for 60 months on a 2025 model", None, R).slots)["model_year"] == 2025
    for question in ("Do certificates auto-renew?", "Can I set up auto-pay for my loan?", "Is there an auto transfer to savings?"):
        assert "auto_loan" not in parse(question, None, R).product_ids, question

# Adversarial W4: an unpublished attribute word is a marker the resolver refuses; the first group beats rate words, the
# last only blocks the rate fallback; card points are a guard (so at 752d164). Ruling 4 (SE4): in a what/which question
# a marker after an explicit rate word modifies it; how and yes/no questions and a marker before it keep the marker.
def test_unpublished_attribute_words_are_markers():
    for question, attribute in (("What is the early withdrawal penalty on the 17-month certificate special?", "penalty"),
                                ("How is the APY on Share Savings compounded?", "compounding"),
                                ("How often are dividends paid on Share Savings?", "frequency"),
                                ("What is the earning rate on the Rewards Visa?", "earning_rate"),
                                ("What rewards does the Platinum Visa earn?", "rewards"), ("What points do I earn on the Rewards Visa?", "points"),
                                ("How long does the 2.90% intro APR last on the Platinum Visa?", "intro_term"),
                                ("Who can open a Launchpad Savings account with $5?", "eligibility"),
                                ("What are the closing costs on a 30-year mortgage?", "closing_costs"),
                                ("What is the down payment for a 15-year mortgage?", "down_payment"),
                                ("What is the credit limit on the Platinum Visa?", "credit_limit"),
                                ("What is the smallest loan amount for a 60-month auto loan?", "loan_amount"),
                                ("What is the rewards rate on the Rewards Visa?", "rewards"),
                                ("How often does the Share Savings rate change?", "frequency"),
                                ("Is the Share Savings APY compounded daily?", "compounding"),
                                ("What is the early withdrawal penalty on the 4.10% APY certificate special?", "penalty")):
        q = parse(question, None, R)
        assert q.attribute == attribute and attribute not in R.published(q.product_id), question
    for question, attribute in (("What is the earning rate on Share Savings?", "apy"), ("What is the rate on a 30-year mortgage?", "rate"),
                                ("Does the highest credit score get the lowest APR on an auto loan?", "apr"),
                                ("What is the 30-year rate with a 20% down payment?", "rate"),
                                ("What is the APY on the 17-month certificate special?", "apy"),
                                ("Is there a fee to open a savings account if I deposit $25?", "fee"),
                                ("What is the APY on Share Savings, compounded monthly?", "apy")):
        assert parse(question, None, R).attribute == attribute, question
    assert [parse(question, None, R).product_id for question in ("What is the rewards rate on the Rewards Visa?",
            "What points do I earn on the Rewards Visa?", "What is the APY on Share Savings, compounded monthly?")] == [
        "rewards_visa", "rewards_visa", "share_savings"]

# Gate review I4, adversarial W2: a list question with no attribute word asks the published rate column; a value one
# only beside an offer/have/list/show word (ruling 1, SE1); otherwise, or with no rate column, description. No loan
# family word exists (reported).
def test_no_attribute_word_asks_the_published_rate_column():
    for want, questions in ((("list", "platinum_visa", "apr"), ("Which credit cards does Dupaco offer?", "What credit cards do you offer?",
                                                                 "What credit cards do you have right now?")),
                            (("list", "share_savings", "apy"), ("What types of savings accounts do you have?",
                                                                 "What savings accounts do you have right now?")),
                            (("list", "cert_regular", "apy"), ("What certificates do you offer?",)),
                            (("list", "first_rate_checking", "apy"), ("What checking accounts do you offer?",)),
                            (("list", "money_market_investors_choice", "apy"), ("What money market accounts do you offer?",)),
                            (("value", "cert_special", "apy"), ("What certificate specials do you have?", "List your certificate specials.",
                                                                 "Show me the certificate specials", "What certificate specials are available?",
                                                                 "What certificate specials are offered?")),
                            (("value", "auto_loan", "apr"), ("What auto loans do you offer?",)),
                            (("value", "share_savings", "description"), ("What is the history of the Share Savings account?",
                                                                         "What is Share Savings?",
                                                                         "What is required to open a savings account?")),
                            (("value", "hsa", "description"), ("What can I use an HSA for?",)),
                            (("value", "platinum_visa", "description"), ("Tell me about the Platinum Visa",)),
                            (("value", "home_start", "description"), ("What is Dupaco's Home$tart program?",)),
                            (("value", "student_loans", "description"), ("Tell me about your student loans",)),
                            (("value", "cert_regular", "description"), ("What do I need to open a CD?",))):  # what opening takes
        for question in questions:
            q = parse(question, None, R)
            assert (q.intent, q.product_id, q.attribute) == want, question
    assert parse("What loans do you offer?", None, R).product_id is None

# Gate review I5: "after the intro period" and its kin ask the standard rate (intro False); "intro" alone the intro one.
def test_after_the_intro_period_is_the_standard_rate():
    for question in ("What APR does the Platinum Visa charge after the intro period?",
                     "What is the Platinum Visa APR after the introductory period?", "What is the HELOC rate once the intro rate ends?",
                     "What's the Platinum Visa APR after the promotional period?", "What is the APR after promo on the Platinum Visa?"):
        assert dict(parse(question, None, R).slots).get("intro") is False, question
    assert dict(parse("What is the intro APR on the Platinum Visa?", None, R).slots).get("intro") is True

# Gate review I6: how_to with a branch/locator word and no financial product asks the branch url; a product keeps its own.
def test_how_to_find_a_branch_asks_the_url():
    for question in ("Where can I find a branch or ATM near me?", "How do I find an ATM near me?",
                     "Where can I find a Dupaco location?", "How can I find the branch locator?"):
        q = parse(question, None, R)
        assert (q.intent, q.product_id, q.attribute) == ("how_to", "branch", "url"), question
    q = parse("How do I open a Share Savings account?", None, R)
    assert (q.intent, q.product_id, q.attribute) == ("how_to", "share_savings", "description")

# Queued fix (a), the addendum, rulings 2 and 3: "website" alone is no url cue; a url noun or "where on the (web)site" is,
# unless unasked beside a rate/phone word and a say/show/list/pay verb; a bare "page" counts only when asked (SE2), and
# "What/Which website has/lists/shows/publishes <X>?" asks the url (SE3).
def test_url_needs_a_url_noun_and_yields_to_what_the_page_says():
    for question, plain in (("According to Dupaco's website, what is the Share Savings APY?", "What is the Share Savings APY?"),
                            ("Per the website, what is the 60-month auto loan APR?", "What is the 60-month auto loan APR?"),
                            ("According to the website, what is the Share Savings APY?", "What is the Share Savings APY?")):
        assert parse(question, None, R).canonical_key == parse(plain, None, R).canonical_key, question
    for question in ("What's the link to the certificate rates page?", "Where on the website can I see certificate rates?",
                     "Which page lists the CD rates?", "What is the URL for the Share Savings?",
                     "Give me the link to the HELOC page.", "Is there a link where I can compare CD rates?",
                     "What page has the HELOC rates?", "Give me the page that lists CD rates", "the page with the auto loan rates",
                     "Is there a page where I can compare CD rates?", "What is the URL of the HELOC rates page?",
                     "What web page shows the CD rates?", "What website has the auto loan rates?", "Which site lists the CD rates?",
                     "What web site shows the HELOC APR?", "Which website publishes the Share Savings rates?",
                     "What web page has the auto loan rates?"):
        assert parse(question, None, R).intent == "url", question
    for question, want in (("What does the web page say about the 36-month personal loan APR?", ("value", "personal_loan", "apr")),
                           ("What does Dupaco's website say the 17-month certificate special pays?", ("value", "cert_special", "apy")),
                           ("What does the website say the 17-month certificate special pays?", ("value", "cert_special", "apy")),
                           ("Is the 17-month certificate special listed on the website?", ("yes_no", "cert_special", "apy")),
                           ("What phone number is on the website?", ("phone", "membership", "phone")),
                           ("What APR does the web page show for the Platinum Visa?", ("value", "platinum_visa", "apr")),
                           ("On the rates page, what is the 60-month auto APR?", ("value", "auto_loan", "apr"))):
        q = parse(question, None, R)
        assert (q.intent, q.product_id, q.attribute) == want, question
    assert dict(parse("On the rates page, what is the 60-month auto APR?", None, R).slots)["term_months"] == 60

# Queued fix (b): a deposit/balance/minimum/opening requirement is min_to_open; "requirements to open" stays eligibility.
def test_deposit_requirement_is_the_opening_minimum():
    q = parse("Is there a deposit requirement of $500 to open Share Savings?", None, R)
    assert (q.intent, q.product_id, q.attribute, dict(q.slots)["amount"]) == ("yes_no", "share_savings", "min_to_open", 500.0)
    for question in ("Is there a balance requirement on Share Savings?", "What are the deposit requirements for a checking account?",
                     "What is the minimum requirement to open a CD?", "What is the minimum deposit requirement for a CD?",
                     "What is the opening deposit requirement for Bright Savings?"):
        assert parse(question, None, R).attribute == "min_to_open", question
    for question in ("What are the membership requirements?", "What are the requirements to open a CD? I want to deposit $1,000."):
        assert parse(question, None, R).attribute == "eligibility", question

# Adversarial W3: an unpriced mortgage program is a program no fact carries (it refuses like the 7/1 ARM).
def test_unpriced_mortgage_programs_are_programs_no_fact_carries():
    for question, program in (("What is the 30-year VA mortgage rate?", "va"), ("What is the 30-year FHA mortgage rate?", "fha"),
                              ("What is the 15-year USDA mortgage rate?", "usda"), ("What is the rate on a second mortgage?", "second"),
                              ("What is the rate on an interest-only mortgage?", "interest_only"),
                              ("What is the mortgage rate for a manufactured home?", "manufactured"),
                              ("What is the mortgage rate on an investment property?", "investment"),
                              ("What is the rate on a reverse mortgage?", "reverse"),
                              ("What is the 30-year fixed mortgage rate?", "purchase")):  # the last one unchanged
        q = parse(question, None, R)
        assert (q.product_id, dict(q.slots)["program"]) == ("mortgage_purchase", program), question
    q = parse("What is the 30-year VA refinance rate?", None, R)
    assert (q.product_id, dict(q.slots)["program"]) == ("mortgage_refi", "va")

# Adversarial W5: fax and email are no phone words; a fax or email question asks an attribute no fact carries.
def test_fax_and_email_are_not_the_phone():
    for question, attribute in (("What's Dupaco's fax number?", "fax"), ("What is Dupaco's email address?", "email")):
        q = parse(question, None, R)
        assert (q.intent, q.attribute) == ("value", attribute), question
    assert parse("What is Dupaco's phone number?", None, R).attribute == "phone"
    assert parse("How can I update my email address?", None, R).intent == "phone"  # own details: the dup-060 ruling

def test_the_facade_passes_the_newest_crawl_as_the_reference(ks_full):
    assert ks_full.explain("What was the 10-month fixed jumbo special certificate rate in May?")["as_of"] == "2026-05-31"

def test_question_date_forms_give_as_of():
    for phrase, want in (("as of May 2026", "2026-05-31"), ("in October 2026", "2026-10-31"),
                         ("on May 31, 2026", "2026-05-31"), ("on 05/31/2026", "2026-05-31"),
                         ("at the end of June 2026", "2026-06-30"), ("on 2026-06-15", "2026-06-15")):
        q = parse("What was the Share Savings APY " + phrase + "?", None, R)
        assert (q.as_of, q.as_of_error) == (want, False), phrase

def test_percent_spelled_out_keeps_the_key():
    a = parse("Is the highest Share Savings APY 0.35%?", None, R)
    b = parse("Is the highest Share Savings APY 0.35 percent?", None, R)
    assert a.canonical_key == b.canonical_key and a.question_numbers == b.question_numbers

def test_arm_ratio_is_never_a_term(public_items):
    question = next(it["question"] for it in public_items if it["id"] == "dup-145")
    slots = dict(parse(question, None, R).slots)
    assert "term_months" not in slots and slots["program"] == "arm"

def test_n_year_fixed_defaults_to_purchase_mortgage():
    for question, months in (("What's the 30-year fixed rate right now?", 360), ("What is the 15 year fixed rate?", 180)):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute, dict(q.slots)["term_months"]) == ("mortgage_purchase", "rate", months)

# Fix round 2: context products yield to family words; superlatives only on rate words.
def test_context_products_yield_to_family_words():
    for question, want, slots in (("What APY does a member earn on savings?", ("share_savings", "apy"), {}),
                                  ("What is the CD rate for a member?", ("cert_regular", "apy"), {}),
                                  ("What rate does a member get on a 24-month certificate?", ("cert_regular", "apy"),
                                   {"term_months": 24}),
                                  ("What's the savings rate at the Galena branch?", ("share_savings", "apy"),
                                   {"branch_name": "galena"})):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute) == want and all(dict(q.slots).get(k) == v for k, v in slots.items()), question

def test_superlative_only_when_it_modifies_a_rate_word():
    q = parse("What is the APY on a $1,000 minimum certificate?", None, R)
    assert dict(q.slots)["amount"] == 1000.0 and "superlative" not in dict(q.slots)
    for question in ("What is the minimum balance to earn the APY on Share Savings?",
                     "What is the maximum balance that earns the APY on Share Savings?"):
        assert "superlative" not in dict(parse(question, None, R).slots), question
    for question, want in (("What is the minimum APR on a personal loan?", "lowest"),
                           ("What's the lowest rate on a car loan?", "lowest"),
                           ("What is the highest Share Savings APY?", "highest"),
                           ("What's the top APY on certificates?", "highest")):
        assert dict(parse(question, None, R).slots).get("superlative") == want, question

# Fix round 3: balance and deposit requirement phrases name min_to_earn / min_to_open and beat rate words.
def test_requirement_phrases_beat_rate_words():
    for question, want in (("What is the minimum balance to earn the APY on Share Savings?", ("share_savings", "min_to_earn")),
                           ("What is the minimum deposit to open a 17-month certificate special?",
                            ("cert_special", "min_to_open")),
                           ("How much do I need to open Share Savings?", ("share_savings", "min_to_open"))):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute) == want and "superlative" not in dict(q.slots), question
    assert dict(parse("What is the minimum deposit to open a 17-month certificate special?", None, R).slots)["term_months"] == 17
    q = parse("What is the least I can deposit to open a CD?", None, R)
    assert q.product_id in ("cert_regular", "cert_special", "ira_cert") and q.attribute == "min_to_open"
    assert "superlative" not in dict(q.slots)
    q = parse("What is the minimum APY on Share Savings?", None, R)
    assert (q.product_id, q.attribute, dict(q.slots).get("superlative")) == ("share_savings", "apy", "lowest")

def test_requirement_phrase_forms():
    for question, attribute in (("What is the minimum balance to earn dividends on Share Savings?", "min_to_earn"),
                                ("What's the minimum balance to earn interest on Share Savings?", "min_to_earn"),
                                ("What is the minimum to open Share Savings?", "min_to_open"),
                                ("What is the minimum balance to open Share Savings?", "min_to_open"),
                                ("What is the minimum amount to open Share Savings?", "min_to_open"),
                                ("What is the minimum opening deposit for Share Savings?", "min_to_open"),
                                ("How much is needed to open Share Savings?", "min_to_open"),
                                ("How much is required to open Share Savings?", "min_to_open"),
                                ("What is the smallest amount to deposit to open Share Savings?", "min_to_open"),
                                ("What is the least amount I can deposit to open Share Savings?", "min_to_open")):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute) == ("share_savings", attribute) and "superlative" not in dict(q.slots), question

# Fix round 4: a two-word requirement phrase ("minimum balance", "opening deposit") yields to the rate word when the
# question carries an amount; lowest/highest/smallest/top need no rate word after them, only no balance/deposit/amount.
def test_two_word_requirement_phrase_yields_to_the_rate_word_beside_an_amount():
    for question, attribute, amount in (
        ("What APY do I earn on Share Savings with a minimum balance of $25,000?", "apy", 25000.0),
        ("What dividend rate applies to Share Savings with a minimum balance of $10,000?", "dividend_rate", 10000.0),
        ("What APY do I get if I open Share Savings with an opening deposit of $500?", "apy", 500.0),
        ("What is the APY on the 17-month certificate with a $1,000 minimum deposit?", "apy", 1000.0),
        ("What is the APY on a $1,000 minimum deposit certificate?", "apy", 1000.0),
        ("What is the APY on a $1,000 minimum balance certificate?", "apy", 1000.0),
    ):
        q = parse(question, None, R)
        assert (q.attribute, dict(q.slots).get("amount")) == (attribute, amount), question
    q = parse("What is the APY for the minimum balance on Share Savings?", None, R)  # no amount: min_to_open (round 3)
    assert (q.product_id, q.attribute) == ("share_savings", "min_to_open")

def test_lowest_highest_smallest_top_need_no_rate_word_after_them():
    for question, want in (("Highest-yielding Share Savings tier", ("share_savings", "apy", "highest")),
                           ("Lowest new car loan rate", ("auto_loan", "apr", "lowest"))):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute, dict(q.slots).get("superlative")) == want, question
    q = parse("Which is the highest paying certificate?", None, R)
    assert (q.intent, dict(q.slots).get("superlative")) == ("value", "highest")
    assert dict(parse("APY for the top Share Savings tier", None, R).slots).get("superlative") == "highest"
    assert parse("Lowest auto loan", None, R).attribute == "apr"
    for question in ("Share Savings with a minimum balance of $25,000",  # guards: inside a requirement phrase,
                     "What is the highest balance tier on Share Savings?",  # before balance/deposit/amount, and
                     "What is the maximum loan amount for a boat loan?"):  # minimum/maximum without a rate word
        assert "superlative" not in dict(parse(question, None, R).slots), question

# Pre-gate wave C. P1: a superlative before a non-rate noun implies no rate; beside both extremes, the rate's wins.
RATE_COLUMNS = {"rate", "apy", "apr", "dividend_rate"}

def test_superlative_before_a_non_rate_noun_implies_no_rate():
    for question in ("What's the highest credit limit on the Platinum Visa?", "What are the lowest closing costs on a mortgage?",
                     "What is the lowest down payment for a mortgage?", "What is the smallest loan amount for a personal loan?",
                     "What's the top reason to open Share Savings?"):
        q = parse(question, None, R)
        assert q.attribute not in RATE_COLUMNS and "superlative" not in dict(q.slots), question
    assert "superlative" not in dict(parse("What's the top of the range for the auto loan APR?", None, R).slots)

def test_the_superlative_beside_the_rate_word_wins():
    for question, want in (("Does the highest credit score get the lowest APR on an auto loan?", "lowest"),
                           ("For the highest model year, what is the lowest auto loan APR?", "lowest"),
                           ("top rate for the lowest term", "highest")):
        assert dict(parse(question, None, R).slots).get("superlative") == want, question
    for question, attribute in (("What is the lowest-cost loan?", None), ("What is the lowest loan rate?", "rate"),
                                ("Lowest new car loan rate", "apr")):  # "cost" and "loan" are not deny-listed
        q = parse(question, None, R)
        assert (q.attribute, dict(q.slots).get("superlative")) == (attribute, "lowest"), question

# P2: "at least" bounds an amount; it is no superlative.
def test_at_least_is_not_a_superlative():
    assert "superlative" not in dict(parse("Do I need at least $1,000 to open a CD?", None, R).slots)
    assert dict(parse("What is the highest APY with at least $1,000?", None, R).slots).get("superlative") == "highest"

# P3: product_ids holds every product in question order, product_id first, and a multi-product key names them all;
# a context product (membership, branch) follows the context rules: dropped beside a financial one, else alone.
def test_product_ids_name_every_product_in_question_order():
    for question, want in (("What are the rates on auto loans and personal loans?", ("auto_loan", "personal_loan")),
                           ("APRs on the Platinum Visa and the auto loan", ("platinum_visa", "auto_loan")),
                           ("Business Platinum Visa and the Platinum Visa", ("business_platinum_visa", "platinum_visa")),
                           ("What are the rates on auto loans and mortgage refinancing?", ("auto_loan", "mortgage_refi"))):
        q = parse(question, None, R)
        assert (q.product_id, q.product_ids, q.canonical_key.split("|")[1]) == (want[0], want, "+".join(want)), question
    for question, want in (("What is the Share Savings APY?", ("share_savings",)),
                           ("What's the savings rate at the Galena branch?", ("share_savings",)),
                           ("What are the hours of the Galena branch?", ("branch",)),
                           ("What's the phone number for auto loans?", ("membership",)),
                           ("What is the weather like?", ())):
        q, pid = parse(question, None, R), (want[0] if want else None)  # one product or none: the key is unchanged
        assert (q.product_id, q.product_ids, q.canonical_key.split("|")[1]) == (pid, want, str(pid)), question

# P4: an "N-year rate" with no product is the purchase mortgage, as "N-year fixed" and ARM wording are.
def test_n_year_rate_defaults_to_purchase_mortgage():
    for question, months in (("Is the 30-year rate 7.27%?", 360), ("What's the 15-year rate?", 180)):
        q = parse(question, None, R)
        assert (q.product_id, q.attribute, dict(q.slots)["term_months"]) == ("mortgage_purchase", "rate", months), question
    q = parse("5-year CD rate", None, R)
    assert (R.family(q.product_id), dict(q.slots)["term_months"]) == ("certificate", 60)

# Wave C fix round 1. Item 1: cheapest/best/greatest/least/most beside the rate word win as the other superlatives do.
def test_other_superlatives_beside_the_rate_word_win():
    for question in ("For the highest model year, what is the cheapest auto loan rate?",
                     "For the highest model year, what is the best auto loan rate?"):
        assert dict(parse(question, None, R).slots).get("superlative") == "lowest", question

# Item 2: needing, requiring or depositing an amount "to open", with no rate word, asks the minimum to open.
def test_an_amount_needed_to_open_asks_the_minimum_to_open():
    for question, amount in (("Do I need at least $1,000 to open a CD?", 1000.0), ("Do I need $500 to open a savings account?", 500.0),
                             ("Is $1,000 required to open a CD?", 1000.0)):
        q = parse(question, None, R)
        assert (q.attribute, dict(q.slots).get("amount")) == ("min_to_open", amount), question
    assert parse("What APY do I get if I deposit $1,000 to open a CD?", None, R).attribute == "apy"  # a rate word: the APY

# Item 3: "at most", like "at least", bounds an amount; it is no superlative.
def test_at_most_is_not_a_superlative():
    slots = dict(parse("What is the APY with at most $5,000 in Share Savings?", None, R).slots)
    assert "superlative" not in slots and slots["amount"] == 4999.99  # an upper bound, read a cent below (fix round 3, F2)

# Fix round 2 (controller ruling): a rate verb (earn, pay, yield) counts as a rate word in the need-to-open check.
def test_a_rate_verb_keeps_an_amount_to_open_a_rate_question():
    q = parse("If I deposit $1,000 to open a CD, how much will I earn?", None, R)
    assert (q.attribute, dict(q.slots).get("amount")) == ("apy", 1000.0)

# Gate fix item 2: IRA wording names the IRA products, never the personal certificate special or the savings family.
def test_ira_certificate_phrasings_name_the_ira_certificate():
    for question in ("What is the APY on the Traditional IRA 10 month fixed jumbo special certificate?",
                     "What is the APY on the Roth IRA 10 month fixed jumbo special certificate?",
                     "What is the APY on the Traditional IRA 17 month fixed special certificate?",
                     "What is the APY on the Roth IRA 10 month certificate special?",
                     "What is the rate on a Roth IRA 18 month regular certificate?", "Traditional IRA jumbo special certificate APY",
                     "What is the APY on the IRA special certificate?", "What is the APY on the IRA jumbo special?",
                     "What is the rate on an IRA CD?"):
        q = parse(question, None, R)
        assert (q.product_id, q.product_ids) == ("ira_cert", ("ira_cert",)), question
    a = parse("What is the APY on the Traditional IRA 10 month fixed jumbo special certificate?", None, R)
    b = parse("What is the APY on the Traditional IRA Certificate 10 month fixed jumbo special?", None, R)
    assert a.canonical_key == b.canonical_key == ("value|ira_cert|apy|[('jumbo', True), ('program', 'traditional'), "
                                                  "('segment', 'personal'), ('special', True), ('term_months', 10)]|None")

def test_ira_savings_phrasings_name_the_variable_ira():
    for question in ("What is the APY on IRA savings?", "What is the APY on a Roth IRA savings account?",
                     "What are the Traditional IRA savings rates?", "What is the IRA variable rate?",
                     "What is the APY on the variable IRA?", "What dividend does a savings IRA pay?"):
        q = parse(question, None, R)
        assert (q.intent, q.product_id, q.product_ids) == ("value", "ira_variable", ("ira_variable",)), question
    assert dict(parse("What is the APY on a Roth IRA savings account?", None, R).slots)["program"] == "roth"

def test_personal_certificates_and_a_bare_ira_keep_their_products():
    q = parse("What is the APY on the 10 month fixed jumbo special certificate?", None, R)
    assert (q.product_id, dict(q.slots).get("jumbo"), dict(q.slots).get("special")) == ("cert_special", True, True)
    assert parse("What is the IRA APY?", None, R).product_ids == ("ira_cert",)  # a bare IRA: the IRA certificate, as before
    q = parse("Compare the 10 month special certificate and the Roth IRA certificate", None, R)
    assert q.product_ids == ("cert_special", "ira_cert")  # an IRA product is named: the comparison keeps both
    assert parse("What is the APY on a traditional savings account?", None, R).product_id == "share_savings"

# Gate fix item 3 (controller ruling): an amount "to open" with a need word asks min_to_open only when the question's
# attribute words are requirement words (none, or min_to_open/min_to_earn); "needed" is a need word.
def test_need_to_open_yields_to_other_attribute_words():
    for question, attribute in (("Is there a fee to open a savings account if I deposit $25?", "fee"),
                                ("What are the requirements to open a CD? I want to deposit $1,000.", "eligibility"),
                                ("I need to open a CD with $5,000. How long is the term?", "term_months")):
        assert parse(question, None, R).attribute == attribute, question
    q = parse("Is $500 needed to open a savings account?", None, R)
    assert (q.intent, q.product_id, q.attribute, dict(q.slots)["amount"]) == ("yes_no", "share_savings", "min_to_open", 500.0)
    assert q.canonical_key == parse("Is $500 required to open a savings account?", None, R).canonical_key

def test_need_to_open_needs_an_amount_to_open_and_a_need_word():
    for question, attribute in (("Do I need to open a savings account with a deposit?", "description"),  # no amount
                                ("Is $500 required for a savings account?", "apy"),  # no "to open"
                                ("Is $500 enough to open a savings account?", "min_to_open")):  # A16: sufficiency cue
        assert parse(question, None, R).attribute == attribute, question
