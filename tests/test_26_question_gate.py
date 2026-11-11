# tests/test_26_question_gate.py
# Phase 2 gate, fix round 2 (the scoped re-review's parser regressions). A new file because tests/test_25_question.py
# is at the 500-line limit.
from kb.question import parse
from kb.registry import Registry
R = Registry.load()

# re-review #1: a site word a URL_ASKERS word claims ("What's the website to join?") asks the site itself (at the end or
# before a SITE_ASKED_NEXT word: fix round 3, F3), and "on the website" in a "where" question asks where; "according
# to the website" and "on the rates page" still ask the value (e2e "qa website", "SE2 on-rates-page")
def test_a_website_asked_for_answers_the_url():
    asks = ("What's the website to join Dupaco?", "What is the website for auto loans?", "Give me the website for the HELOC.",
            "Where can I find certificate rates on the website?", "Which site has the auto loan rates?",
            "Where on the website can I find certificate rates?", "What website has the auto loan rates?")
    assert [q for q in asks if (parse(q, None, R).intent, parse(q, None, R).attribute) != ("url", "url")] == []

def test_a_website_named_as_the_source_still_asks_the_value():
    asks = ("According to Dupaco's website, what is the Share Savings APY?", "On the rates page, what is the 60-month auto APR?",
            "What is the website's rate for the 17-month special certificate?", "What's the site's APY on Share Savings?",
            "What does the site say the Share Savings APY is?")
    assert [q for q in asks if parse(q, None, R).intent != "value"] == []

# fix round 2c: a site or page word written possessive ("the website's 17-month rate", "the web page's APR") names the
# source, never the thing asked, whatever follows it, so the value answers (the first four as at base); a url noun
# after it still asks the url ("the website's URL"), and so does "where ... on the website's ..." (fix round 3, F4)
def test_a_possessive_site_word_never_asks_the_url():
    asks = ("What's the website's 17-month rate?", "What is the site's current APY?",
            "What is the website's current Share Savings APY?", "Find the website's 60-month auto rate",
            "What is the web page's APR on the HELOC?", "What's the webpage's rate for Share Savings?")
    assert [q for q in asks if parse(q, None, R).intent != "value"] == []
    assert parse("What is the website's URL for auto loans?", None, R).intent == "url"

# re-review #2: an amount after "under", "below", "less than", "up to", "fewer than" or before "or less", "and under",
# "and below" is an upper bound, read a cent below it: it reaches no inclusive minimum to earn (the jumbo row's
# $100,000) and stays in a tier that ends at it; "or more", "at least" and a bare amount read as written
def test_an_upper_bound_amount_reads_a_cent_below_it():
    def amount(phrase): return dict(parse("What is the 17-month special certificate rate for %s?" % phrase, None, R).slots)["amount"]
    below = ("up to $100,000", "$100,000 or less", "under $100,000", "below $100,000", "less than $100,000",
             "fewer than $100,000", "$100,000 and under", "$100,000 and below")
    assert {p: amount(p) for p in below} == {p: 99999.99 for p in below}
    assert dict(parse("If I keep $25,000 or less in Share Savings, what APY do I earn?", None, R).slots)["amount"] == 24999.99
    as_written = {"$100,000 or more": 100000.0, "at least $100,000": 100000.0, "$150,000": 150000.0}
    assert {p: amount(p) for p in as_written} == as_written

# re-review #4: a past word before "owned" or "model", and "prior" before "to", is no past cue ("previously owned
# vehicle", "prior model year", "prior to"): no past walk; "What was the previous rate ...", "before it changed", "prior
# to the change" are
def test_previously_owned_and_prior_model_year_are_no_past_cue():
    vehicle = ("What is the APR on a 60-month loan for a previously owned vehicle?", "What's the rate for a prior model year car?",
               "What is the 60-month auto rate for a previous model year vehicle?")
    assert [q for q in vehicle if parse(q, None, R).past] == []
    past = ("What was the previous rate on the 17-month special certificate?",
            "What did the 17-month special certificate pay before it changed?",
            "What was the APY prior to the change on the 17-month special certificate?")
    assert [q for q in past if not parse(q, None, R).past] == []

# fix round 3, F1: only "prior to" is no past cue; "previous to the latest update" asks the old value, as at base
def test_previous_to_is_a_past_cue():
    assert not parse("What is the 17-month special rate prior to maturity?", None, R).past  # "prior to" stays none
    asks = ("What was the 17-month special APY previous to the latest update?", "What was the 17-month special APY previous to September?",
            "What was the 10-month jumbo special APY previous to the last update?")
    assert [q for q in asks if not parse(q, None, R).past] == []

# fix round 3, F2: a negated lower bound ("no less than", "not under", "no fewer than", "nothing less than") is no upper
# bound, so it reads as written; "at most", "no more than", "not more than", "a maximum of", "max", "no greater than",
# "not exceeding" and "capped at" are upper bounds, read a cent below
def test_negated_lower_bounds_read_as_written_and_more_upper_bounds_read_below():
    def amount(phrase): return dict(parse("What is the 17-month special certificate rate for %s?" % phrase, None, R).slots)["amount"]
    assert (amount("less than $100,000"), amount("at least $100,000")) == (99999.99, 100000.0)  # as before
    negated = ("no less than $100,000", "not less than $100,000", "not under $100,000", "not below $100,000",
               "no fewer than $100,000", "nothing less than $100,000")
    upper = ("at most $100,000", "no more than $100,000", "not more than $100,000", "a maximum of $100,000", "max $100,000",
             "no greater than $100,000", "not exceeding $100,000", "a deposit capped at $100,000")
    assert {p: amount(p) for p in negated + upper} == {**{p: 100000.0 for p in negated}, **{p: 99999.99 for p in upper}}

# fix round 3, F3: a site word a URL_ASKERS word claims asks the site only at the end of the question or before a
# SITE_ASKED_NEXT word ("to", "for", "where", "should" ...); before a verb or a product word it names the source and the
# value answers ("What is the website showing for the HELOC APR?", "What's the website HELOC APR?"), as at base. A bare
# "on site" is a place, not the website ("Where is the ATM on site at the Key West branch?")
def test_a_site_word_asks_the_url_only_before_an_asking_word():
    keeps = ("What is the website?", "Is there a website where I can see mortgage rates?", "What website should I visit for CD rates?")
    assert [q for q in keeps if parse(q, None, R).intent != "url"] == []  # as before
    values = ("What is the website listing for the Share Savings APY?", "What is the website showing for the HELOC APR?",
              "What's the website quoting for the 60-month auto loan APR?", "What's the website offering on the 17-month special certificate?",
              "What is the website advertising for the HELOC APR?", "What's the website saying the HELOC APR is?",
              "What is the website displaying for the Share Savings APY?", "What's the website posting for 60-month auto loan rates?",
              "What is the website stating as the HELOC APR?", "What is the website currently showing for the Share Savings APY?",
              "What is the website now showing for the 17-month special APY?", "What's the website HELOC APR?",
              "What's the website 17-month special rate?", "Where is the ATM on site at the Key West branch?",
              "Where can I park on site at the Asbury branch?")
    assert [q for q in values if parse(q, None, R).intent == "url"] == []

# fix round 3, F4: "on <site word>" in a where question asks the url even when the site word is possessive ("Where on
# the website's contact page is the ATM locator?"; the possessive exemption keeps only the URL_ASKERS rule and the
# what/which-has rule), and "where's" is "where" ("Where's the HELOC APR on the website?")
def test_where_on_a_possessive_site_word_asks_the_url():
    assert parse("What's the website's 17-month rate?", None, R).intent == "value"  # the possessive rule otherwise holds
    asks = ("Where on the website's contact page is the branch and ATM locator?",
            "Where on the website's membership page can I join online?", "Where on the site's join page do I apply for membership?",
            "Where on the website's home page do I join Dupaco?", "Where on the website's savings page are the certificate rates?",
            "Where on the website's rates page can I find the HELOC APR?", "Where's the HELOC APR on the website?",
            "Where's the certificate rates page on the website?")
    assert [q for q in asks if parse(q, None, R).intent != "url"] == []

# fix round 3, F6: an incidental past word in a current question is no past cue: a past word before "year(s)" or
# "owner(s)" ("prior-year model", "previous owner"), and "previously"/"formerly" before an -ed word, "took" or "had" ("a
# previously leased car", "if I previously had a loan") unless "was", "were" or "did" comes earlier
def test_incidental_past_words_in_current_questions_are_no_past_cue():
    keeps = ("Which certificate specials were previously offered?", "What did the 17-month special previously pay?",
             "What was the 17-month special APY previously?")
    assert [q for q in keeps if not parse(q, None, R).past] == []  # as before
    current = ("What's the current 60-month auto loan rate for a previously leased car?",
               "What is the 60-month auto loan APR to refinance a car previously financed elsewhere?",
               "What's the 60-month auto rate on a car with a previous owner?", "What is the 60-month APR for a prior-year model car?",
               "What is the APR for a previous year's model on a 60-month auto loan?",
               "What's the 60-month auto rate on a formerly leased vehicle?",
               "What rate do you offer on a 60-month loan for a previously titled vehicle?",
               "What rate do you offer on a 60-month loan for a previously registered vehicle?",
               "What's the 60-month auto APR for a 2025 car if I previously had a loan with you?",
               "What's the 60-month rate to refinance an auto loan I previously took out elsewhere?")
    assert [q for q in current if parse(q, None, R).past] == []

# fix round 3, F3 follow-up: "on Dupaco's site" is no bare "on site": the tokenizer skips the brand word between them,
# which made "Where on Dupaco's site ...?" lose its url (corpus probes2 url-14, rereview2 where:122)
def test_on_the_brand_site_is_the_website():
    assert parse("Where is the ATM on site at the Key West branch?", None, R).intent != "url"  # F3 holds
    asks = ("Where on Dupaco's site can I see the auto loan rates?", "Where on Dupaco's site can I join online?")
    assert [q for q in asks if parse(q, None, R).intent != "url"] == []

# fix round 4, N1: more ways of asking for the website keep the url: a claimed site word before "is", "with", "called",
# "am", "id" (I'd) or "youd" (you'd), and "what/which website" before "offers", "gives", "contains", "lets" and kin; the
# F3 value questions still ask the value
def test_more_ways_of_asking_for_the_website_ask_the_url():
    asks = ("Which website offers the branch and ATM locator?", "What website gives Dupaco's CD rates?", "Which site lets me join online?",
            "What website is used to join Dupaco online?", "What's the website with the branch locator?", "What is the website with the CD rates?",
            "Which website contains certificate rates?", "What site is the ATM locator on?", "What website am I supposed to use to join?",
            "What's the website called where I can join?", "What's the website I'd use to join?", "What's the website you'd recommend for CD rates?")
    assert [q for q in asks if (parse(q, None, R).intent, parse(q, None, R).attribute) != ("url", "url")] == []
    values = ("What is the website showing for the HELOC APR?", "What's the website offering on the 17-month special certificate?",
              "What's the website saying the HELOC APR is?")
    assert [q for q in values if parse(q, None, R).intent != "value"] == []  # as before

# fix round 4, N2: a written model-year range ("2024-2027", "2021 to 2023") keeps both ends in model_year_range beside
# model_year, which reads as before (the year beside the vehicle or "model year" words); a single year sets no range
def test_a_written_model_year_range_keeps_both_ends():
    def years(q): return tuple(dict(parse(q, None, R).slots).get(n) for n in ("model_year", "model_year_range"))
    got = {q: years(q) for q in ("What was the previous 60-month auto loan APR for the 2024-2027 model years?",
                                 "What was the previous APR on a 60-month auto loan for 2021-2023 model years?",
                                 "What used to be the 72-month auto loan APR for a 2021 to 2023 model?",
                                 "What was the previous 60-month auto loan APR for model year 2024-2027?",
                                 "What is the 60-month auto loan APR for the 2024-2027 model years?",
                                 "What was the previous 60-month auto loan APR for a 2027 model year?")}
    assert list(got.values()) == [(2027, (2024, 2027)), (2023, (2021, 2023)), (2023, (2021, 2023)), (2024, (2024, 2027)),
                                  (2027, (2024, 2027)), (2027, None)]

# fix round 4, F6 leftover: a "was", "were" or "did" whose subject is the member or the member's vehicle ("if the car was
# previously leased", "if I was previously approved") keeps no history clause a past cue, while one about the rate or
# the product does ("Which certificate specials were previously offered?"); "previously been ..." tells history like an
# -ed word unless a "has", "have" or "had" about the rate comes first ("What has the 17-month special previously been?")
def test_a_later_was_or_previously_been_is_no_past_cue():
    current = ("What is the 60-month auto APR for a car that has previously been financed?",
               "What's the 60-month auto rate if the car was previously leased?",
               "What is the 60-month auto loan rate for a vehicle that was previously financed elsewhere?",
               "What is the 60-month auto APR if I was previously approved for a loan?",
               "What is the 60-month auto APR for a vehicle that has previously been titled in another state?",
               "What rate do you charge on a 60-month loan for a car that's previously been leased?",
               "If the car was previously leased, what's the 60-month auto rate?")
    assert [q for q in current if parse(q, None, R).past] == []
    past = ("What was the previous rate on the 17-month special?", "What did the 17-month special pay before it changed?",
            "Which certificate specials were previously offered?", "What APY was previously offered on the 17-month special?",
            "What has the 17-month special previously been?", "Can you tell me which certificate specials were previously offered?",
            "Do you know what APY was previously offered on the 17-month special?")
    assert [q for q in past if not parse(q, None, R).past] == []

# fix round 4, F6 leftover follow-up: a "was" in a later clause about the rate or the product still asks the past, as on
# d204bb9 ("the APY that was previously offered", "the rate the 17-month special was previously offered at"); only a
# subject that is the member or the member's vehicle (the word before it, "that", "which" or "who" skipped) tells history
def test_a_was_about_the_rate_stays_a_past_cue():
    past = ("What is the APY that was previously offered on the 17-month special?",
            "What's the rate the 17-month special was previously offered at?",
            "What is the rate that was previously quoted for the 17-month special?",
            "What's the APY the 17-month special was formerly listed at?")
    assert [q for q in past if not parse(q, None, R).past] == []
    current = ("What's the 60-month auto rate for members who were previously approved?",
               "For a car that was previously leased, what's the 60-month auto rate?",
               "What is the 60-month auto APR if I have previously been approved for a loan?")
    assert [q for q in current if parse(q, None, R).past] == []

# fix round 4, N4: a past word right before "year" with no model or vehicle word after it ("in the previous year", "the
# prior year") asks a date one year back (slot year_back), no past value; "a prior-year model car" and "the previous
# year's model" ("years") name a model year and set no slot
def test_the_previous_year_asks_a_date_one_year_back():
    asks = ("What was the 17-month special APY in the previous year?", "What did the 17-month special pay in the prior year?",
            "What was the APY on Share Savings the previous year?")
    assert [q for q in asks if (dict(parse(q, None, R).slots).get("year_back"), parse(q, None, R).past) != (True, False)] == []
    models = ("What is the 60-month APR for a prior-year model car?", "What is the APR for a previous year's model on a 60-month auto loan?",
              "What is the 60-month auto rate for a prior year vehicle?")
    assert [q for q in models if "year_back" in dict(parse(q, None, R).slots)] == []

# fix round 4, N5: more upper bounds before the amount ("a max of", "maximum", "not greater than", "not to exceed", "up
# to and including", "no higher than", "not over") read a cent below it, and a bound phrase starts at a word boundary,
# so "climax $100,000" and "setup to $100,000" read as written
def test_more_upper_bounds_read_below_and_a_bound_starts_a_word():
    def amount(q): return dict(parse(q, None, R).slots)["amount"]
    upper = ["What is the 17-month special certificate rate %s $100,000?" % p for p in (
        "for a max of", "for maximum", "for not greater than", "not to exceed", "for up to and including", "for no higher than",
        "for not over")]
    written = ["What is the 17-month special certificate rate for %s $100,000?" % p for p in ("climax", "setup to")]
    assert {q: amount(q) for q in upper + written} == {**{q: 99999.99 for q in upper}, **{q: 100000.0 for q in written}}

# fix round 5, R1: "previously"/"formerly" before a rate participle ("the previously offered APY", "the previously
# advertised rate", "the APY previously offered on ...") asks the old value, as at 7ff32f7, while before "leased",
# "financed" or "owned" it still tells the member's history, and "prior model year" names a model year
def test_previously_before_a_rate_participle_is_a_past_cue():
    past = ("What is the previously offered APY on the 17-month special?", "What is the previously advertised rate for the 17-month special?",
            "What's the previously quoted 17-month special APY?", "What's the previously posted rate for the 17-month special certificate?",
            "Tell me the previously advertised 17-month special APY.", "Show me the previously listed APY for the 17-month special.",
            "What is the APY previously offered on the 17-month special?", "What's the 17-month special's previously published APY?",
            "What is the previously advertised 60-month auto loan APR for a 2025 car?", "What is the formerly offered APY on the 10-month jumbo special?",
            "Give me the previously stated APY for the 17-month special.")
    assert [q for q in past if not parse(q, None, R).past] == []
    current = ("What's the 60-month auto rate if the car was previously leased?", "What is the APR on a 60-month loan for a previously owned vehicle?",
               "What's the rate for a prior model year car?", "What is the 60-month auto loan APR to refinance a car previously financed elsewhere?")
    assert [q for q in current if parse(q, None, R).past] == []  # as before

# fix round 5, D: "between 2024 and 2027" is a written model-year range too ("and" joins the range words); "from 2021 to
# 2023" reads as before, and model_year stays the year beside the vehicle words
def test_between_two_model_years_is_a_range():
    def years(q): return tuple(dict(parse(q, None, R).slots).get(n) for n in ("model_year", "model_year_range"))
    got = [years(q) for q in ("What was the previous 60-month auto loan APR for between 2024 and 2027 model years?",
                              "What was the previous 60-month auto loan APR for between 2021 and 2023 model years?",
                              "What was the previous 60-month auto loan APR for from 2021 to 2023 model years?")]
    assert got == [(2027, (2024, 2027)), (2023, (2021, 2023)), (2023, (2021, 2023))]

# Phase 3 Task 12: hours wording, bare branch names, phone words beside a lobby cue, other-hours markers
def _route(q, as_of=None): p = parse(q, as_of, R); return (p.intent, p.product_id, p.attribute)

def test_hours_routes():
    for q in ("What are the lobby hours at Dupaco branches?", "When are Dupaco's lobbies open?", "What time do Dupaco branches open?", "Lobby hours?"):
        assert _route(q) == ("hours", "branch", "lobby_hours"), q
    for q in ("What are Dupaco's drive-up hours?", "When is the drive-thru open?", "Drive up window hours?", "How late is the drive-up open?"):  # (pin)
        assert _route(q) == ("hours", "branch", "driveup_hours"), q

def test_bare_branch_names_bind_the_branch_slot():  # controller ruling 2026-11-06, from Lane H's report
    cases = {"What are the drive-up hours in Galena?": "galena", "What are the lobby hours in Dubuque?": "dubuque",
             "Lobby hours at Key West?": "flint hill", "What are the Platteville lobby hours?": "platteville",
             "What time does the drive-up in Platteville close?": "platteville", "What are the hours at Dupaco in Waukee?": "waukee",
             "Which branch should Hy-Vee members use instead?": "hy-vee"}
    for q, name in cases.items():
        assert dict(parse(q, None, R).slots).get("branch_name") == name, q

def test_branch_names_cover_every_branch_fact(store_full):
    from kb.lexicon import BRANCH_NAMES
    names = {dict(f.qualifiers)["branch_name"] for (pid, _), fs in store_full.by_product_attr["05_2026-09-28_latest"].items()
             if pid == "branch" for f in fs if "branch_name" in dict(f.qualifiers)}
    assert [n for n in sorted(names) if not any(b in n for b in BRANCH_NAMES)] == []

# Task 11 review: a phone word beside a lobby or drive-up cue asks the phone number (an hours word keeps the hours, as
# the contact form's reply hours do); an hours question about anything but branch lobby or drive-up hours asks the
# marker other_hours, which no product publishes
def test_phone_words_beat_a_lobby_cue_and_other_hours_are_a_marker():
    for q in ("What is the phone number for the Platteville branch lobby?", "What number do I call for the Waukee branch lobby?",
              "What is the phone number for the drive-up?", "lobby phone number for Mars"):
        assert _route(q)[0] == "phone", q
    assert _route("What hours can I call Dupaco?") == ("hours", "membership", "reply_hours")  # (pin)
    for q in ("What are your holiday hours?", "What are the safe deposit box hours?", "What were the lobby hours before the remodel?",
              "Is the drive-up open 24 hours?"):
        assert _route(q)[2] == "other_hours", q

# Task 12 review I2: "when ... open" asked of a branch, "you" or Dupaco, "When can I come in?" and "open ... at the same
# time(s)" ask the lobby hours; "when ... close" never does (a closure date: the status route, Task 13), nor a past
# opening or "open" with an object; a bare branch name is branch context ("Where is Dupaco in Galena?" asks the address)
def test_opening_wordings_ask_the_hours_and_closing_ones_do_not():
    for q in ("When are Dupaco branches open?", "When are your branches open?", "When are you open?", "When does Dupaco open?",
              "When can I come in?", "Do all Dupaco branches open and close at the same time?",
              "Are all Dupaco locations open at the same times?"):
        assert _route(q) == ("hours", "branch", "lobby_hours"), q
    for q in ("When do you close?", "When did the Waukee branch open?", "When can you open my account?"):
        assert _route(q)[0] != "hours", q
    assert _route("When does the Hy-Vee branch close?") == ("status", "branch", "closure_date")  # (pin) Task 13's closure route
    galena, hy_vee = parse("Where is Dupaco in Galena?", None, R), parse("Is Hy-Vee still open?", None, R)
    assert (galena.intent, galena.product_id, dict(galena.slots).get("branch_name")) == ("address", "branch", "galena")
    assert (hy_vee.intent, hy_vee.product_id, dict(hy_vee.slots).get("branch_name")) == ("status", "branch", "hy-vee")

# Task 12 review M2: two or more bare branch names bind none (every schedule, as at base) until Task 17's multi-branch
# slot, and stay branch context; a name inside a longer one is one name
def test_two_bare_branch_names_bind_none():
    for q in ("Are the Cedar Rapids and Waukee lobby hours the same?", "What are the lobby hours in Grimes and Waukee?",
              "Do Cedar Falls, Grimes and Waukee have the same lobby hours?", "When are Grimes and Waukee open?",
              "Are the lobby hours in Grimes the same as in Waukee?"):
        p = parse(q, None, R)
        assert (p.intent, "branch_name" in dict(p.slots)) == ("hours", False), q
    assert dict(parse("What are the Mineral Point Road lobby hours?", None, R).slots)["branch_name"] == "mineral point road"  # (pin)
    for q, name in (("What are the drive-up hours at the Hy-Vee in Dubuque?", "hy-vee"),  # a branch and its city: the first
                    ("What are the lobby hours at East Washington in Madison?", "east washington")):
        assert dict(parse(q, None, R).slots).get("branch_name") == name, q
# Phase 3 Task 13: closures and alternatives
def test_closure_and_alternative_routes():
    for q in ("When is the Hy-Vee branch closing?", "What date does the Dupaco Hy-Vee branch close?", "When will the branch in Hy-Vee shut down?"):  # (pin)
        assert _route(q) == ("status", "branch", "closure_date"), q
    for q in ("Where can Hy-Vee branch members go for full-service banking?", "Which branch should Hy-Vee members use instead?"):
        p = parse(q, None, R)
        assert (p.intent, p.product_id, p.attribute, dict(p.slots).get("branch_name")) == ("value", "branch", "alternatives", "hy-vee"), q
    p = parse("When is Dupaco closing its Hy-Vee location?", None, R)  # "its" ends the name, as "the" does
    assert (_route("When is Dupaco closing its Hy-Vee location?"), dict(p.slots).get("branch_name")) == (
        ("status", "branch", "closure_date"), "hy-vee")

def _routed(q): p = parse(q, None, R); return (p.intent, p.product_id, p.attribute, dict(p.slots).get("branch_name"))

def test_bare_branch_names_bind_status_questions():  # Task 12 carry: on its tree "Is Hy-Vee still open?" parses yes_no|None
    assert _routed("Is Hy-Vee still open?") == ("status", "branch", "status", "hy-vee")
    assert _routed("When does Hy-Vee close?") == ("status", "branch", "closure_date", "hy-vee")
    assert _routed("When does the Hy-Vee branch close?") == ("status", "branch", "closure_date", "hy-vee")  # (pin)
    assert _routed("What time does Hy-Vee close?") == ("hours", "branch", "lobby_hours", "hy-vee")  # (pin) hours wording keeps the hours
    assert _routed("Is the savings rate at Galena still 0.20%?")[:2] == ("yes_no", "share_savings")  # (pin) no status word: no status
    assert _routed("Will the Marion share certificate close?")[:2] == ("value", None)  # (pin) a product word, even an unknown product's

def test_a_status_question_naming_no_branch_asks_the_closures_only_with_a_closure_word():  # review: on 2533337 these list both closures
    for q in ("Is the branch open today?", "Are branches open on holidays?", "Are Dupaco branches open on Thanksgiving?",
              "Is the branch open on Christmas Day?", "When does the branch close?", "Is the branch closed on Christmas?"):
        assert _route(q) == ("status", "branch", "other_hours"), q  # the marker no product publishes: refused
    for q in ("Which branches have closed?", "Are any branches closing?"):  # (pin)
        assert _route(q) == ("status", "branch", "status"), q
    assert _routed("Is the Hy-Vee branch open on Christmas?") == ("status", "branch", "status", "hy-vee")  # (pin)

def test_closing_costs_are_no_status_cue():  # review: on 2533337 "What's the branch closing cost?" lists both closures
    for q in ("Does the branch have a closing cost?", "What's the branch closing cost?", "What are the closing costs at the Galena branch?"):
        assert _route(q)[0] != "status" and _route(q)[2] == "closing_costs", q  # the marker: refused
    assert _route("Is the Galena branch closing?") == ("status", "branch", "status")  # (pin)

def test_the_alternatives_cue_needs_a_branch_value_question_naming_a_branch():
    assert _routed("What is the savings rate at the Galena branch instead?")[2] != "alternatives"  # savings publish no alternatives
    assert _routed("Which branch should I go to instead?")[2] is None  # (pin) no branch named
    assert _routed("What are the lobby hours at the nearest branch to Galena?")[:3] == ("hours", "branch", "lobby_hours")  # (pin)
    assert _routed("Can Hy-Vee branch members go to another branch?")[0] == "yes_no"  # (pin) the cue never sets the intent
