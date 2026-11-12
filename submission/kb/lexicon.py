"""Vocabulary of the question canonicaliser (``question.py``): synonyms, word sets, month tables and bounded regexes.

Data only, standard library only. Phrases and words are lowercase word tokens as ``question.py`` makes them
(apostrophes dropped, ``Home$tart`` joined, ``dupaco`` skipped). Every regex runs on ``norm_text`` output, where
each whitespace run is one space, and none nests a quantifier or holds an unbounded whitespace run, so each one is
linear in the cut question.
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

INTENTS = ("value", "list", "yes_no", "url", "how_to", "status", "count", "change", "hours", "address", "phone",
           "routing")


def _syn(kind: str, target: str, *phrases: str) -> Dict[str, Tuple[str, str]]:
    return {phrase: (kind, target) for phrase in phrases}


# "(least | smallest | minimum) (amount)? (I can | to) deposit to open": the opening-deposit requirement.
_DEPOSIT_TO_OPEN = tuple(" ".join(w for w in (head, amount, verb, "deposit to open") if w)
                         for head in ("least", "smallest", "minimum") for amount in ("", "amount")
                         for verb in ("i can", "to"))


# phrase -> (kind, target). "product": a named product, as strong as a registry alias; "weak": a product word that
# yields to any named product; "family": a generic family word (FAMILY_IDS), resolved by segment and wording, that
# also marks a list question; "attribute". Each phrase also matches with a trailing "s" ("cds", "rates").
SYNONYMS: Dict[str, Tuple[str, str]] = {
    **_syn("family", "certificate", "cd", "cert", "certificate", "share certificate", "term certificate",
           "term share certificate", "certificate of deposit", "month special", "month jumbo", "jumbo special"),
    **_syn("family", "credit_card", "credit card", "visa", "visa card", "visa credit card"),
    **_syn("family", "checking", "checking", "checking account"),
    **_syn("family", "savings", "savings", "savings account"),
    **_syn("family", "money_market", "money market", "money market account"),
    **_syn("product", "auto_loan", "car loan", "auto loan", "vehicle loan",  # an auto refinance is the auto loan
           *(vehicle + " " + refi for vehicle in ("auto", "car", "vehicle")
             for refi in ("refinance", "refi", "refinancing"))),
    **_syn("product", "membership", "aba", "aba number", "routing number", "routing"),
    **_syn("product", "heloc", "heloc", "home equity line", "home equity line of credit"),
    **_syn("product", "home_equity", "home equity"),
    **_syn("product", "mortgage_purchase", "mortgage", "home loan"),
    **_syn("product", "cash_out_refi", "cash out", "cash out refinance", "cash out refi"),
    **_syn("product", "achieve_money_market", "achieve"),
    **_syn("weak", "mortgage_refi", "refinance", "refi", "refinancing"),
    **_syn("weak", "ira_cert", "ira"),
    **_syn("product", "ira_variable", "ira savings", "ira variable", "savings ira"),  # "Roth IRA savings account"
    **_syn("weak", "auto_loan", "auto", "car", "vehicle", "truck", "suv", "motorcycle"),  # not before AUTO_COMPOUNDS
    **_syn("weak", "boat_rv_loan", "boat", "rv"),
    **_syn("weak", "branch", "locator", "location"),
    **_syn("weak", "mobile_wallet", "wallet"),
    **_syn("attribute", "apy", "apy", "yield", "annual percentage yield"),
    **_syn("attribute", "dividend_rate", "dividend", "dividend rate"),
    **_syn("attribute", "apr", "apr", "annual percentage rate"),
    **_syn("attribute", "rate", "rate", "interest rate", "interest"),
    **_syn("attribute", "min_to_open", "minimum", "min", "minimum deposit", "minimum balance", "minimum to open",
           "min to open", "opening deposit", "minimum deposit to open", "minimum balance to open",
           "minimum amount to open", "minimum opening deposit", "how much do i need to open",
           "how much is needed to open", "how much is required to open", *_DEPOSIT_TO_OPEN,
           # "requirement" right after deposit/balance/minimum/opening is the opening minimum (queued fix (b))
           "deposit requirement", "balance requirement", "minimum requirement", "min requirement",
           "opening requirement", "minimum deposit requirement", "minimum balance requirement",
           "opening deposit requirement"),
    **_syn("attribute", "min_to_earn", "minimum to earn", "min to earn", "minimum balance to earn"),
    **_syn("attribute", "points", "points"),
    **_syn("attribute", "payment_example", "monthly payment"),
    **_syn("attribute", "fee", "fee"),
    **_syn("attribute", "cash_advance", "cash advance", "cash-advance", "cashadvance"),
    **_syn("attribute", "term_months", "term"),
    **_syn("attribute", "eligibility", "eligible", "eligibility", "qualify", "requirement", "who can open",
           "who may open"),
    # Attribute words no product publishes (adversarial W4): markers the resolver refuses; see ATTR_PRIORITY.
    **_syn("attribute", "penalty", "penalty", "penalties", "early withdrawal", "early withdrawal penalty",
           "withdrawal penalty"),
    **_syn("attribute", "compounding", "compounding", "compounded", "compound", "compounds"),
    **_syn("attribute", "frequency", "how often"),
    **_syn("attribute", "rewards", "rewards", "reward", "rewards rate", "reward rate", "cash back", "cashback"),
    **_syn("attribute", "earning_rate", "earning rate", "earn rate", "earnings rate"),  # a deposit's: its APY
    **_syn("attribute", "closing_costs", "closing cost"),
    **_syn("attribute", "down_payment", "down payment"),
    **_syn("attribute", "credit_limit", "credit limit"),
    **_syn("attribute", "credit_score", "credit score"),
    **_syn("attribute", "loan_amount", "loan amount", "loan limit"),
    **_syn("attribute", "features", "reason", "benefit", "feature", "perk"),
    **_syn("attribute", "income", "income"),
    **_syn("attribute", "age", "age"),
    **_syn("attribute", "fax", "fax", "fax number"),  # no fax or general email on the site (W5)
    **_syn("attribute", "email", "email", "email address", "e mail"),
}
# One-word attribute phrases and their plurals: a registry alias ending in one ("auto loan rates", "member
# eligibility") is stored without it, so the word still reaches the attribute rules.
ATTRIBUTE_WORDS = frozenset(word for phrase, (kind, _) in SYNONYMS.items() if kind == "attribute" and " " not in phrase
                            for word in (phrase, phrase if phrase.endswith("s") else phrase + "s"))
FAMILY_IDS = {"certificate": ("cert_regular", "business_cert_regular"),  # family -> (personal id, business id)
              "credit_card": ("platinum_visa", "business_platinum_visa"),
              "checking": ("first_rate_checking", "business_checking"),
              "savings": ("share_savings", "business_savings"),
              "money_market": ("money_market_investors_choice", "business_money_market")}
REMAP = {"routing_number": "membership"}  # controller ruling: contact facts are stored under membership
# IRA wording: a certificate family word beside one is the IRA certificate, and so is a named personal certificate
# ("Traditional IRA 10 month fixed jumbo special certificate": no phrase spans the term) unless an IRA product is named.
IRA_WORDS = frozenset({"ira", "iras", "roth", "traditional"})
IRA_TWINS = {"cert_regular": "ira_cert", "cert_special": "ira_cert"}
IRA_PRODUCTS = frozenset({"ira_cert", "ira_variable"})
CONTEXT = frozenset({"branch", "branch_count", "membership", "contact_page", "rates_page", "website"})
COUNT_NOUNS = {**dict.fromkeys(("branch", "branches", "office", "offices", "location", "locations"), "branch_count"),
               **dict.fromkeys(("employee", "employees", "staff"), "employee_count"),
               **dict.fromkeys(("county", "counties"), "county_count")}
DATED_COUNT_PRODUCTS = frozenset({"employee_count", "county_count", "branch_count", "vto_users", "volunteer_hours"})
# "X and Y <head>" ("the Platinum and Rewards Visa", "boat and personal loans"): when "Y <head>" and "X <head>" both
# name products, both are asked. The head opens with one of these words; X is at most three words before the
# coordinator.
COORDINATORS = frozenset({"and", "or"})
COORD_HEADS = frozenset({"visa", "visas", "card", "cards", "certificate", "certificates", "loan", "loans", "savings",
                         "checking"})
MORTGAGE_IDS = frozenset({"mortgage_purchase", "mortgage_refi", "cash_out_refi"})
REFI_WORDS = frozenset({"refinance", "refi", "refinancing"})  # "mortgage" with one of these: the refinance product
# Mortgage programs the site does not price (adversarial W3): the program slot no fact carries, so they refuse like ARM.
UNPRICED_PROGRAMS = (("va", ("va",)), ("fha", ("fha",)), ("usda", ("usda",)), ("interest_only", ("interest", "only")),
                     ("second", ("second", "mortgage")), ("second", ("second", "mortgages")),
                     ("second", ("2nd", "mortgage")), ("manufactured", ("manufactured",)),
                     ("investment", ("investment", "property")), ("investment", ("investment", "properties")),
                     ("reverse", ("reverse", "mortgage")), ("reverse", ("reverse", "mortgages")))
HOME_LENDING = frozenset({"mortgage_refi", "cash_out_refi", "mortgage_rate_relief", "construction_loan", "home_start"})
LOAN_WORDS = frozenset({"loan", "loans", "lending", "borrow", "borrowing", "financing"})
# "auto"/"autos" right before one of these is no auto loan ("auto-pay", "auto-renew", "auto transfer").
AUTO_COMPOUNDS = frozenset({"pay", "pays", "payment", "payments", "renew", "renews", "renewal", "renewals", "renewing",
                            "renewed", "transfer", "transfers", "debit", "debits", "deposit", "deposits", "draft",
                            "drafts", "save", "saves", "insurance", "matic"})
LOAN_HINTS = {"student": "student_loans", "students": "student_loans", "college": "student_loans",
              "university": "student_loans", "tuition": "student_loans", "school": "student_loans",
              "construction": "construction_loan", "model": "auto_loan"}
# Words that may sit capitalised right before a family word without naming an unknown product.
KNOWN_CAPS = frozenset({"the", "a", "an", "my", "your", "our", "any", "all", "each", "on", "for", "of", "in", "at",
                        "to", "with", "about", "and", "or", "what", "which", "is", "are", "month", "months", "year",
                        "years", "fixed", "jumbo", "special", "regular", "standard", "business", "personal", "roth",
                        "traditional", "share", "term", "new", "current", "best", "top", "highest", "lowest"})
AUX = frozenset({"is", "are", "does", "do", "can", "did", "was", "were", "has", "have"})
WH = frozenset({"what", "whats", "which", "how", "when", "where", "who", "why"})
REQUEST_VERBS = frozenset({"tell", "give", "show", "provide", "list", "share", "send", "find", "get", "repeat",
                           "confirm", "explain", "check", "look"})
CHANGE_WORDS = frozenset({"change", "changed", "changes", "changing", "increase", "increased", "decrease",
                          "decreased", "rise", "rose", "risen", "fell", "fallen", "dropped", "happened", "happen", "happens"})
MODALS = frozenset({"may", "might", "can", "could", "will", "would", "should", "to"})  # "rates may change"
COMPARE_WORDS = frozenset({"different", "difference", "differ", "compare", "compared", "versus", "vs"})
# Past-value wording (Query.past, the contract with the resolver): a PAST_WORDS word not before a NOT_PAST_NEXT word
# ("previously owned vehicle", "prior model year": re-review #4; "previous owner", "prior-year model": fix round 3, F6),
# "prior" not before "to" ("previous to the latest update" is a cue: F1), and no PAST_ADVERBS history clause (below,
# F6); "used to" unless it is the passive
# (normalize.passive_used_to: a USED_TO_PASSIVE word right before it, or a BE_FORMS word earlier with no USED_TO_CLAUSE
# word between, as in "What is the HSA used to pay for?"); "old" right before a rate
# word; "before" or "prior to", one to four PAST_FILLER words and a past change: a PAST_CHANGED verb ("went"/"gone" with
# up/down), or a PAST_CHANGE noun after a PAST_NOUN_LEAD word ("before the change", "before the last rate change"; a
# plural noun only right after a determiner, so "before the rate changes" is the verb). Those change words then are no
# change cue. A passive "used to" asks a purpose, so it never falls back to the rate either (qslots.attribute).
PAST_WORDS = frozenset({"previous", "previously", "prior", "formerly"})
NOT_PAST_NEXT = frozenset({"owned", "model", "year", "years", "owner", "owners"})
# A PAST_ADVERBS word before an -ed word, a HISTORY_VERBS word or "been" tells the member's own history, no past value
# ("a car previously financed elsewhere", "if I previously had a loan", "a car that's previously been leased"), unless a
# PAST_ASKED word comes earlier ("Which specials were previously offered?", "the APY that was previously offered"; fix
# round 3, F6), or before "been" a PERFECT_HEADS word ("What has the 17-month special previously been?"). Such a word
# whose subject (the word before it, a RELATIVE_WORDS word skipped) is a HISTORY_SUBJECTS word, the member or the
# member's vehicle, asks nothing ("if the car was previously leased", "if I was previously approved", "a vehicle that
# has previously been titled"; fix round 4, F6 leftover). A RATE_PARTICIPLES word is no -ed word here: "the previously
# offered APY", "the previously advertised rate" ask the old value (fix round 5, R1).
PAST_ADVERBS = frozenset({"previously", "formerly"})
HISTORY_VERBS = frozenset({"took", "had"})
RATE_PARTICIPLES = frozenset({"offered", "advertised", "quoted", "posted", "listed", "published", "stated", "featured",
                              "promoted", "displayed", "mentioned", "charged", "earned", "priced"})
PAST_ASKED = frozenset({"was", "were", "did"})
PERFECT_HEADS = frozenset({"has", "have", "had"})
RELATIVE_WORDS = frozenset({"that", "which", "who"})
BE_FORMS = frozenset({"is", "are", "was", "were", "be", "been", "being", "am", "whats", "thats", "its"})
USED_TO_PASSIVE = BE_FORMS | {"get", "gets", "got", "getting"}
USED_TO_CLAUSE = frozenset({"it", "they", "that", "which", "who", "we", "i", "you", "he", "she"})
PAST_FILLER = frozenset({"it", "its", "the", "this", "that", "they", "rate", "rates", "apy", "apr", "yield", "dividend",
                         "interest", "last", "latest", "most", "recent", "was", "were", "had"})
PAST_DETERMINERS = frozenset({"the", "this", "that", "its", "last", "latest", "recent"})
PAST_NOUN_LEAD = PAST_DETERMINERS | {"rate", "apy", "apr", "yield", "dividend", "interest"}
PAST_CHANGED = frozenset({"changed", "increased", "decreased", "rose", "risen", "fell", "fallen", "dropped", "went",
                          "gone"})
PAST_CHANGE = frozenset({"change", "changes", "increase", "increases", "decrease", "decreases", "drop", "rise"})
UPDOWN = (("go", "up"), ("go", "down"), ("went", "up"), ("went", "down"), ("gone", "up"), ("gone", "down"))
HOWTO_SEQS = (("how", "do", "i"), ("how", "can", "i"), ("how", "to"), ("how", "would", "i"), ("how", "should", "i"),
              ("how", "do", "you"), ("where", "can", "i"), ("where", "do", "i"))
CHANGE_BLOCK = HOWTO_SEQS + (("can", "i"), ("could", "i"), ("change", "of"))
# Url cues (queued fix (a)): a url noun (URL_WORDS, URL_SEQS); "on the (web)site" in a question with "where" or
# "where's", possessive or not ("Where can I find the rates on the website?", "Where on the website's contact page is
# the ATM locator?": fix round 3, F4; a bare "on site" is a place: "the ATM on site", F3); a SITE_WORDS word a
# URL_ASKERS word claims across URL_FILLER words, at the end of the question or before a SITE_ASKED_NEXT word ("What's
# the website to join?"; before a verb or a product word it names the source: "What is the website showing for the
# HELOC APR?", F3). "website"/"site" alone is none ("According to Dupaco's website, ..."; re-review #1), and outside
# "where ... on" a site word or url noun written possessive is none whatever follows it ("the website's 17-month
# rate", "the web page's APR": the source, not the thing asked; fix round 2c). A url noun
# that no URL_ASKERS word claims across URL_FILLER words ("Which page", "give me the link") yields to an explicit rate
# or phone word beside a SAY_VERBS verb: "What does the web page say about the APR?" asks the APR (the adversarial
# addendum).
URL_WORDS = frozenset({"url", "urls", "link", "links", "webpage", "webpages", "page", "pages"})
URL_SEQS = (("web", "page"), ("web", "pages"), ("web", "address"), ("web", "addresses"))
SITE_WORDS = frozenset({"website", "websites", "site", "sites"})
# "What/Which website has/lists/shows/publishes ...?" asks the site itself (integration ruling 3, SE3), and so do
# "offers", "gives", "contains", "lets" and kin ("Which website offers the branch locator?": fix round 4, N1).
SITE_VERBS = frozenset({"has", "have", "lists", "list", "shows", "show", "publishes", "publish", "offers", "offer",
                        "gives", "give", "contains", "contain", "provides", "provide", "lets", "let", "hosts", "host",
                        "carries", "carry", "includes", "include"})
# The words after a claimed SITE_WORDS word that keep it the thing asked ("" is the end of the question): "the website
# to join", "the website for auto loans", "a website where I can ...", "the website address" (fix round 3, F3); "the
# website with the CD rates", "What site is the ATM locator on?", "the website called ...", "the website I'd / you'd
# ..." ("id", "youd" once the apostrophe is dropped) (fix round 4, N1).
SITE_ASKED_NEXT = frozenset({"", "to", "for", "where", "that", "which", "i", "you", "we", "do", "does", "did", "should",
                             "can", "could", "would", "will", "address", "addresses", "url", "link", "of", "is", "with",
                             "called", "am", "id", "youd"})
# A bare "page" (no "web" before it) is a url noun only when asked: a URL_ASKERS word before it, or one of these after
# it ("the page that lists CD rates"); "On the rates page, what is the APR?" asks the APR (integration ruling 2, SE2).
PAGE_FOLLOWERS = frozenset({"that", "where", "with", "for", "which"})
URL_FILLER = frozenset({"the", "a", "an", "your", "our", "its", "this", "that", "me", "us", "is", "are", "official",
                        "main", "direct", "exact", "correct", "right", "web"})
URL_ASKERS = frozenset({"what", "whats", "which", "where", "wheres", "give", "send", "share", "provide", "need", "want",
                        "get", "find", "have", "there", "show", "see", "visit"})
SAY_VERBS = frozenset({"say", "says", "said", "show", "shows", "showed", "shown", "list", "lists", "listed", "pay",
                       "pays", "paid", "display", "displays", "displayed", "state", "states", "stated", "mention",
                       "mentions", "mentioned"})
NUMBER_NOUNS = frozenset({"phone", "telephone", "fax", "routing", "aba", "account", "member", "contact", "toll"})
ADDRESS_WORDS = frozenset({"address", "addresses", "located", "directions"})
PHONE_WORDS = frozenset({"phone", "telephone", "call", "contact"})  # fax and email are no phone (W5): markers
UPDATE_WHAT = frozenset({"address", "contact", "phone", "email", "name", "information", "info"})
REPLY_WORDS = frozenset({"reply", "replies", "respond", "responds", "response"})
REPLY_CUES = REPLY_WORDS | {"contact", "phone", "call", "calls", "message", "messages", "email"}
DRIVE_SEQS = (("drive", "up"), ("drive", "thru"), ("drive", "through"), ("drive", "in"))
# Hours cues (qslots.keyword_intent): an HOURS_WORDS word always; a LOBBY_WORDS word or a DRIVE_SEQS sequence only with
# no PHONE_WORDS word ("the phone number for the Platteville branch lobby" asks the phone: Task 11 review). A lobby word
# is branch context too (question.parse), so a lobby question never asks the contact form's reply hours.
HOURS_WORDS = frozenset({"hours", "hour"})
LOBBY_WORDS = frozenset({"lobby", "lobbies"})
# "When ... open" asks the hours (qslots.asks_opening) after one of these, never after a past or future verb ("When did
# the Waukee branch open?" asks a date), and never with one of OPEN_OBJECTS after "open" ("When can you open my
# account?").
OPEN_ASKERS = frozenset({"are", "is", "do", "does", "can"})
OPEN_OBJECTS = frozenset({"a", "an", "my", "your", "our", "new", "another", "account", "accounts"})
# Hours no branch lobby or drive-up schedule gives (Task 11 review): an hours question holding one of these words or
# sequences asks the marker attribute other_hours, which no product publishes, so the resolver refuses it. Named
# holidays and the weather too (Task 12 review C1: "Are lobbies open on Memorial Day?"), as the tokens read them:
# "New Year's" is new years, "July 4th" july 4th, "the 4th of July" 4th of july; and the categories' synonyms (I1:
# "safety deposit box", "customer support", "online banking"; never "online" alone, as in "the lobby hours online").
OTHER_HOURS_WORDS = frozenset({"holiday", "holidays", "christmas", "thanksgiving", "atm", "atms", "coin", "coins",
                               "summer", "winter", "seasonal", "headquarters", "hq", "remodel", "remodeling",
                               "renovation", "memorial", "juneteenth", "veterans", "presidents", "independence",
                               "easter", "mlk", "weather", "snow", "snowstorm", "storm", "blizzard", "itm", "itms",
                               "notary"})
OTHER_HOURS_SEQS = (("safe", "deposit"), ("customer", "service"), ("member", "service"), ("member", "services"),
                    ("service", "center"), ("call", "center"), ("night", "deposit"), ("night", "drop"),
                    ("corporate", "office"), ("corporate", "offices"), ("24", "hour"), ("24", "hours"), ("24", "7"),
                    ("labor", "day"), ("new", "year"), ("new", "years"), ("fourth", "of", "july"),
                    ("4th", "of", "july"), ("july", "4"), ("july", "4th"), ("martin", "luther"), ("good", "friday"),
                    ("black", "friday"), ("columbus", "day"), ("safety", "deposit"), ("customer", "support"),
                    ("customer", "care"), ("main", "office"), ("night", "depository"), ("member", "center"),
                    ("support", "center"), ("video", "teller"), ("drop", "box"), ("online", "banking"),
                    ("mobile", "banking"))
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_WORDS = frozenset(DAYS + tuple(d + "s" for d in DAYS))
BRANCH_WORDS = frozenset({"branch", "branches", "location", "locations", "office", "offices"})
# Branch names a question may write without a branch word (controller ruling 2026-11-06, from Lane H's report): the
# /contact page's streets and cities, the newsroom hours articles' branches, and the branches the site names elsewhere
# (Hy-Vee, Key West, Asbury, Mullan Avenue, Coralville; Marion, Waterloo and Edgewood Road, which the crawl text names
# with a branch word; Carroll, Dyersville and Manchester: Task 12 review M4). normalize.bare_branch reads the one name
# written (two or more bind none); qslots.slots binds it as the branch_name of a question whose product is branch,
# where a name no branch fact carries refuses (resolve._branch_unlisted), and any name is branch context.
BRANCH_NAMES = frozenset({"asbury", "carroll", "cedar falls", "cedar rapids", "coralville", "dubuque", "dyersville",
                          "east washington", "edgewood road", "flint hill", "galena", "grimes", "hillcrest", "hy-vee",
                          "key west", "madison", "manchester", "marion", "mineral point", "mineral point road",
                          "mullan", "mullan avenue", "oldenburg", "pennsylvania", "peosta", "platteville", "sycamore",
                          "waterloo", "waukee"})
# Between two bare branch names, one of these lists several branches ("the Cedar Rapids and Waukee lobby hours", "in
# Grimes the same as in Waukee"), so normalize.bare_branch binds none; any other words name one branch and its city
# ("the Hy-Vee in Dubuque"), the first written. A comma alone joins none: the site writes "Hillcrest Rd., Dubuque".
NAME_JOINERS = frozenset({"and", "or", "nor", "&", "vs", "versus", "plus", "as", "than", "with", "compared"})
# A how_to question with one of these (or "near me") and no financial product asks the branch locator's url (I6).
LOCATOR_WORDS = frozenset({"branch", "branches", "atm", "atms", "location", "locations", "locator", "locators"})
STATUS_WORDS = frozenset({"closed", "closing", "closure", "closures", "close", "closes", "reopen", "reopened",
                          "reopening", "permanently", "shut", "operating"})
NOT_STATUS_PAIRS = frozenset({("closing", "cost"), ("closing", "costs"), ("close", "to")})
CLOSURE_DATE_WORDS = frozenset({"when", "date"})  # a status question with one asks closure_date (compose_prose too)
# The alternatives cue (qslots.attribute, Task 13): in a value question naming a branch of a product that publishes
# alternatives (only branch does), one of these words or sequences asks where its members can go instead ("Where can
# Hy-Vee branch members go for full-service banking?", "Which branch should Hy-Vee members use instead?").
ALTERNATIVE_WORDS = frozenset({"go", "instead", "alternative", "alternatives", "nearest", "nearby"})
ALTERNATIVE_SEQS = (("full", "service"),)
LIST_CUES = frozenset({"all", "every", "which", "offer", "offers", "options", "types", "kinds", "products", "accounts",
                       "cards", "loans", "rates", "aprs", "apys", "yields", "terms", "cds", "certificates"})
TIER_SLOTS = ("term_months", "amount", "model_year", "superlative")
# The unpublished markers (W4) of the first group beat the rate words ("How often are dividends paid?", "How is the APY
# compounded?") unless a what/which question names the rate word first, which they then modify ("What is the APY on
# Share Savings, compounded monthly?", SE4); those of the last only keep a question without another attribute word off
# the rate ("the lowest APR for the highest credit score" asks the APR). "how long" beside INTRO_WORDS is the marker
# intro_term (qslots.py).
RATE_BEATING = ("cash_advance", "penalty", "compounding", "frequency", "rewards", "earning_rate", "fax", "email")
ATTR_PRIORITY = RATE_BEATING + ("apy", "dividend_rate", "rate", "apr", "min_to_earn", "min_to_open", "points",
                                "payment_example", "fee", "term_months", "eligibility",
                 "closing_costs", "down_payment", "credit_limit", "credit_score", "loan_amount", "features", "income",
                 "age")
INTRO_WORDS = frozenset({"intro", "introductory", "promotional", "promo"})
# "after the intro period", "once the promotional rate ends": the standard rate (extract_rules._AFTER_INTRO_RE).
AFTER_INTRO_RE = re.compile(r"\b(?:after|once) (?:the |an |its |your |my )?(?:promo(?:tional)?|intro(?:ductory)?)\b")
INTENT_ATTRIBUTE = {"routing": "routing_number", "phone": "phone", "address": "address", "count": "count",
                    "url": "url"}
RATE_ATTRS = frozenset({"apy", "dividend_rate", "rate", "apr"})
# A multi-word phrase naming one of these ("minimum balance to earn", "how much do I need to open") beats rate words;
# a two-word one ("minimum balance", "opening deposit") only when the question carries no amount, because "the APY
# with a minimum balance of $25,000" asks the APY at that balance.
REQUIREMENT_ATTRS = frozenset({"min_to_open", "min_to_earn"})
# With no requirement phrase and no attribute word but a REQUIREMENT_ATTRS one (controller ruling: "Is there a fee to
# open a savings account if I deposit $25?" keeps the fee, a term or eligibility word its own), an amount "to open"
# beside one of these asks min_to_open ("Do I need $500 to open a savings account?", "Is $500 needed to open ...?").
NEED_WORDS = frozenset({"need", "needs", "needed", "require", "requires", "required", "deposit", "deposits"})
# With "to open" and no attribute word, one of these asks what opening takes, not the rate: "What is required to open
# a savings account?" keeps description (W2's rate default skips it).
REQUIRE_VERBS = frozenset({"need", "needs", "needed", "require", "requires", "required"})
# A value question with no attribute word asks the rate column only beside one of these (integration ruling 1, SE1):
# "What certificate specials do you have?" asks the APY, "What is the history of Share Savings?" keeps description.
OFFER_WORDS = frozenset({"offer", "offers", "offered", "offering", "offerings", "have", "list", "show", "available",
                         "types", "kinds"})
# The rate verbs that also block it (controller ruling): "If I deposit $1,000 to open a CD, how much will I earn?"
# asks the rate.
EARN_WORDS = frozenset({"earn", "earns", "earning", "pay", "pays", "paying", "yield", "yields"})
# Superlatives (controller rulings): a RATE_SUPERLATIVES word never counts after a number ("$1,000 minimum") or inside
# a multi-word attribute phrase ("minimum balance to earn"). An ADJACENT_SUPERLATIVES word (minimum, maximum) counts
# only when it modifies a rate word, with product words and fillers allowed between ("minimum APY", "the maximum
# current APR"); the others (lowest, highest, smallest, top) count unless the first word after any product words and
# fillers is an AMOUNT_NOUNS or NON_RATE_NOUNS word or opens a NON_RATE_PAIRS pair ("lowest balance", "highest credit
# limit", "lowest closing costs"), or "top" is followed by "of", so "highest-yielding Share Savings tier" and "lowest
# auto loan" keep theirs. The OTHER_SUPERLATIVES count wherever they stand ("most" only when a rate is asked), but no
# word counts in a NOT_SUPERLATIVE_PAIRS pair ("at least", "at most"). "best"/"top" mean lowest for a loan, highest
# otherwise. When several count, the one that modifies a rate word wins ("the highest credit score ... the lowest
# APR", "the cheapest auto loan rate").
RATE_SUPERLATIVES = {"minimum": "lowest", "min": "lowest", "lowest": "lowest", "smallest": "lowest",
                     "maximum": "highest", "max": "highest", "highest": "highest", "top": "best"}
ADJACENT_SUPERLATIVES = frozenset({"minimum", "min", "maximum", "max"})
AMOUNT_NOUNS = frozenset({"balance", "balances", "deposit", "deposits", "amount", "amounts"})
NON_RATE_NOUNS = frozenset({"reason", "reasons", "limit", "limits", "score", "scores", "benefit", "benefits",
                            "feature", "features", "perk", "perks", "income", "age"})
NON_RATE_PAIRS = frozenset({("credit", "limit"), ("credit", "limits"), ("credit", "score"), ("credit", "scores"),
                            ("closing", "cost"), ("closing", "costs"), ("down", "payment"), ("down", "payments"),
                            ("loan", "amount"), ("loan", "amounts"), ("loan", "limit"), ("loan", "limits")})
OTHER_SUPERLATIVES = {"greatest": "highest", "most": "highest", "cheapest": "lowest", "least": "lowest", "best": "best"}
NOT_SUPERLATIVE_PAIRS = frozenset({("at", "least"), ("at", "most")})  # (previous word, word): they bound an amount
SUPERLATIVE_FILLER = frozenset({"the", "a", "an", "current", "possible", "available"})
PRODUCT_KINDS = ("product", "weak", "family")  # SYNONYMS kinds that name a product
RATE_VERBS = frozenset({"pay", "pays", "paying", "earn", "earns", "earning", "charge", "charges", "cost"})
VEHICLE_WORDS = frozenset({"model", "car", "cars", "vehicle", "vehicles", "truck", "trucks", "suv", "suvs",
                           "motorcycle", "motorcycles", "van", "minivan", "auto"})
# normalize.model_year_range: "a 2021 to 2023 model", "between 2021 and 2023 model years" (fix round 5, D)
YEAR_RANGE_WORDS = frozenset({"to", "through", "thru", "and"})
HISTORY_SUBJECTS = VEHICLE_WORDS | {"i", "we", "member", "members"}  # see PAST_ADVERBS: the member, the member's car
NAME_STOP = frozenset({"the", "a", "an", "your", "our", "my", "at", "for", "of", "in", "on", "to", "from", "near",
                       "by", "with", "and", "or", "is", "are", "was", "does", "do", "did", "can", "could", "will",
                       "where", "when", "what", "which", "how", "many", "much", "any", "all", "each", "every", "other",
                       "same", "this", "that", "one", "nearest", "closest", "local", "main", "new", "general",
                       "dupaco", "lobby", "drive-up", "drive-thru", "full-service", "atm", "atms", "closed", "open",
                       "about", "if", "whether", "there", "its", "their"})  # "closing its Hy-Vee location" (Task 13)
NAME_PUNCT = "?.,!;:()[]\"'"
MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "may": 5,
          "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
          "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}  # no bare "apr": APR
QUAL_DAY = {"mid": 15, "middle": 15, "early": 1, "beginning": 1, "start": 1}  # end/late/none: the last day
DATE_LEAD = frozenset({"in", "of", "by", "since", "between", "and", "from", "to", "until", "till", "through",
                       "during", "before", "after", "on", "vs", "versus", "or"})
MODAL_LEADS = frozenset({"and", "or"})  # "... and may I": a bare "may" here with a word after it is the verb
MONTH_RE = re.compile(r"\b(?:(end|late|mid|middle|early|beginning|start)(?: of | |-))?("
                      + "|".join(sorted(MONTHS, key=lambda name: (-len(name), name)))
                      + r")\b\.?(?: (\d{1,2})(?:st|nd|rd|th)?\b)?(?:,? (?:of )?(\d{4})\b)?")
NUM_DATE_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])|(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
YEAR_MONTH_RE = re.compile(r"(?<![\d/$.,-])(\d{4})-(\d{1,2})(?![\d/,-])")  # "as of 2026-05", after a DATE_LEAD word
TERM_RE = re.compile(r"(?<![\d.,$/])(\d{1,3}) ?-? ?(months?|mos?|years?|yrs?)\b")
TERM_RATE_RE = re.compile(r"[ -](?:interest )?rates?\b")  # matched where TERM_RE ends: "the 30-year rate"
AMOUNT_RE = re.compile(r"(?:\$ ?|(?=\d[\d,]*(?:\.\d+)?\s*(?:k|m|thousand|million|dollars)\b))(\d[\d,]*)(\.\d+)?(?: ?(thousand|million|k|m)\b)?(?:\s*dollars\b)?")
# Upper-bound wording around an asked amount (re-review #2), which ``normalize.question_amount`` reads a cent below:
# starting in the 24 characters before AMOUNT_RE's match ("under $100,000", "at most $100,000"), never right after
# "no", "not" or "nothing" ("no less than $100,000" is a lower bound; fix round 3, F2), or matched where that match
# ends ("$100,000 or less", "$100,000 and under"). A phrase before the amount starts a word ("climax $100,000" and
# "setup to $100,000" read as written); "a max of", "maximum", "not greater than", "not to exceed", "up to and
# including", "no higher than" and "not over" are bounds too (fix round 4, N5).
UPPER_BOUND_BEFORE_RE = re.compile(r"(?<!\bno )(?<!\bnot )(?<!\bnothing )\b(?:under|below|less than|"
                                   r"up to(?: and including)?|fewer than|at most|no more than|not more than|"
                                   r"(?:a )?max(?:imum)?(?: of)?|no greater than|not greater than|no higher than|"
                                   r"not exceeding|not to exceed|not over|capped at) $")
UPPER_BOUND_AFTER_RE = re.compile(r" (?:or|and) (?:less|under|below)\b")
ARM_RE = re.compile(r"(?<![\d/])(?:3|5|7|10)/(?:1|6)(?![\d/])")
APOSTROPHE_RE = re.compile("['`\\u2018\\u2019\\u201b\\u2032]")
HOMESTART_RE = re.compile(r"home\$tart", re.I)
WORD_RE = re.compile(r"[A-Za-z0-9]+")
BRAND = frozenset({"dupaco", "dupacos"})
RANK = {"product": 0, "weak": 1, "family": 2, "attribute": 3}
LONGEST = 8  # tokens in the longest phrase looked up
