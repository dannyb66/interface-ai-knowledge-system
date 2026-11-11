# tests/test_10_extract.py  (section A)
from pathlib import Path
import json
from kb.pagetype import classify, authority_of

S05 = Path("snapshots/05_2026-09-28_latest")
def page(file): return (S05 / file).read_text(encoding="utf-8")

def test_classify_real_pages():
    assert classify("https://www.dupaco.com/rates", page("pages/rates-59a9e6.md")) == "rate_sheet"
    assert classify("https://www.dupaco.com/personal/savings-account", page("pages/personal-savings-account-7ef72e.md")) == "product_page"
    assert classify("https://www.dupaco.com/calculators/vehicle-affordability", page("pages/calculators-vehicle-affordability-bc054b.md")) == "calculator"
    assert classify("https://www.dupaco.com/contact", page("pages/contact-c99539.md")) == "contact"

def test_authority_classes():
    assert authority_of("rate_sheet") == authority_of("product_page") == 3 and authority_of("calculator") == 1 and authority_of("blog") == 0


# tests/test_10_extract.py  (section B)
from kb.blocks import split_blocks, load_boilerplate

def test_table_block_takes_following_effective_line():
    blocks = [b for b in split_blocks(page("pages/rates-59a9e6.md"), load_boilerplate()) if b.kind == "table"]
    specials = next(b for b in blocks if any("17 Month Fixed Certificate Special" in l for l in b.lines))
    assert specials.effective_date == "2026-09-01" and specials.heading_path[-1]
    share = next(b for b in blocks if any("| Share Savings | $25,000+" in l for l in b.lines))
    assert share.effective_date == "2026-06-15"

def test_adjacent_tables_keep_their_own_dates():
    dates = [b.effective_date for b in split_blocks(page("pages/rates-59a9e6.md"), load_boilerplate()) if b.kind == "table"]
    assert len(set(d for d in dates if d)) >= 5

def test_table_without_effective_line_orders_oldest():
    md = "## Fees\n| Fee | Amount |\n| --- | --- |\n| Wire | $25.00 |\n\nSome prose.\n"
    (tbl,) = [b for b in split_blocks(md, frozenset()) if b.kind == "table"]
    assert tbl.effective_date is None

def test_table_rows_infer_columns_and_skip_headerless():
    from kb.blocks import table_rows
    blocks = [b for b in split_blocks(page("pages/rates-59a9e6.md"), load_boilerplate()) if b.kind == "table"]
    auto = next(b for b in blocks if any("| 2024-27 Model Year | 60 Months |" in l for l in b.lines))
    rows = table_rows(auto)
    assert rows[0].columns == ("label", "term", "apr") and any(r.label == "2024-27 Model Year" and r.cells[1] == "60 Months" for r in rows)
    headerless = split_blocks("| 5.19% APR | 48 Months |\n| 5.39% APR | 60 Months |\n", frozenset())[0]
    assert table_rows(headerless) == []

def test_variable_ira_rows_keep_their_ira_type():
    from kb.blocks import table_rows
    md = Path("snapshots/01_2026-05-12_baseline/pages/rates-59a9e6.md").read_text(encoding="utf-8")
    ira = next(b for b in split_blocks(md, load_boilerplate()) if b.kind == "table" and any("Traditional: $15,000+" in l for l in b.lines))
    rows = table_rows(ira)
    assert rows[0].columns[0] == "label" and next(r for r in rows if "| Roth: $15,000+ |" in r.raw).label == "Roth: $15,000+"

def test_table_header_tells_duplicate_kinds_apart():
    from kb.blocks import table_header, table_rows
    achieve = next(b for b in split_blocks(page("pages/earn-more-3ae90d.md"), load_boilerplate()) if b.kind == "table" and any("Achieve Money Market" in l for l in b.lines))
    header, cols = table_header(achieve), table_rows(achieve)[0].columns
    assert len(header) == len(cols) and cols.count("dividend_rate") == 2
    assert [h for h, c in zip(header, cols) if c == "dividend_rate"] == ["Dividend Rate for 1st 6 Months", "Dividend Rate After Promotional Period"]
    assert table_header(next(b for b in split_blocks(page("pages/rates-59a9e6.md"), load_boilerplate()) if b.kind == "prose")) == ()

def _tables(md): return [b for b in split_blocks(md, frozenset()) if b.kind == "table"]
def _prose_lines(blocks): return [l for b in blocks if b.kind == "prose" for l in b.lines]

def test_trailer_keeps_effective_and_footnote_lines_and_leaves_prose():
    note = "1 Boat & RV Loan Rates: Loan annual percentage rates (APR) based on member credit qualification."
    example = "Boat & RV loan payment example: If you borrow $50,000 at a 7.09% annual percentage rate (APR) for 60 months, your payment is $992.45."
    md = ("Boat & RV Loans\n\n| Loan Amount | Term | APR |\n| --- | --- | --- |\n| $40,000+ | 60 Months | 7.09% |\n\n"
          + example + "\n\n" + note + "\n\nRates effective 01/01/2023. All loans are subject to approval.\n")
    blocks = split_blocks(md, frozenset())
    (tbl,) = [b for b in blocks if b.kind == "table"]
    assert [l for l in tbl.lines if not l.startswith("|")] == [note, "Rates effective 01/01/2023. All loans are subject to approval."]
    assert (tbl.effective_date, tbl.footnotes) == ("2023-01-01", (note,))
    prose = _prose_lines(blocks)
    assert example in prose and note in prose  # a footnote stays visible to the inline pass
    assert not any(l.startswith("Rates effective") for l in prose)
    blocks = split_blocks(page("pages/earn-more-3ae90d.md"), load_boilerplate())
    achieve = next(b for b in blocks if b.kind == "table" and any("Achieve Money Market" in l for l in b.lines))
    tail = [l for l in achieve.lines if not l.startswith("|")]  # its footnote and its "As of, 8/24/26" rate sentence
    assert len(tail) == 2 and tail[0].startswith("\\*APY=Annual Percentage Yield") and "As of, 8/24/26" in tail[1]
    prose = _prose_lines(blocks)
    assert "Previous" in prose and tail[1] in prose and any(l.startswith('> "The staff is always') for l in prose)

def _date_of(trailer): return _tables("| Account Type | APY |\n| --- | --- |\n| Achieve Money Market | 3.25% |\n\n" + trailer)[0].effective_date

def test_table_date_comes_only_from_a_date_cue():
    assert _date_of("New Money is money not on deposit with Dupaco since 08/24/2026.\n") is None
    assert _date_of("\\*New Money is money not on deposit with Dupaco since 08/24/2026.\n") is None
    assert _date_of("Offer valid through 12/31/2026. Rates effective 09/01/2026.\n") == "2026-09-01"
    assert _date_of("Offer valid through 12/31/2026.\nRates effective 09/01/2026.\n") == "2026-09-01"
    assert _date_of("Rates effective immediately. Offer valid through 12/31/2026.\n") is None  # same sentence only
    (prose,) = [b for b in split_blocks("Offer valid through 12/31/2026. Rates effective 09/01/2026.\n", frozenset())]
    assert prose.effective_date == "2026-09-01"  # the rule prose uses

def test_as_of_rate_sentence_dates_a_table_like_an_effective_line():
    as_of = ("As of, 8/24/26, the tiered introductory rate structure is as follows: $0.00-$24,999.99 at 0.00% dividend rate "
             "and 0.00% APY; $25,000.00-99,999.99 at 4.00% dividend rate and 3.66% APY.")
    assert _date_of(as_of + "\n") == "2026-08-24"
    (prose,) = split_blocks(as_of + "\n", frozenset())
    assert prose.effective_date == "2026-08-24"  # prose alike
    for bare in ("Offer valid through 12/31/2026.", "**04/08/2020**", "Updated 3/1/2026", "As of today, we have 24 branches.",
                 "As of 09/01/2026, we have 24 branches.", "As of 09/01/2026, our records are accurate."):
        assert _date_of(bare + "\n") is None, bare
    for snapshot, file in (("05_2026-09-28_latest", "earn-more-3ae90d.md"), ("04_2026-08-27_rebaseline", "rates-59a9e6.md"),
                           ("04_2026-08-27_rebaseline", "personal-savings-account-7ef72e.md")):
        blocks = split_blocks((Path("snapshots") / snapshot / "pages" / file).read_text(encoding="utf-8"), load_boilerplate())
        promo = [b for b in blocks if b.kind == "table" and "Dividend Rate for 1st 6 Months" in b.lines[0]]
        assert [b.effective_date for b in promo] == ["2026-08-24"], (snapshot, file)
        assert any("As of, 8/24/26" in l for l in _prose_lines(blocks)), (snapshot, file)  # the rate sentence stays prose

def _prose_date(text): return [b.effective_date for b in split_blocks(text + "\n", frozenset())]

def test_as_of_cue_skips_a_title_case_rate_inside_a_name():
    fhlb = "Update: As of July 17, 2024 at 3:00 PM CST, all funds for the FHLB Mortgage Rate Relief program have been allocated."
    assert _date_of(fhlb + "\n") is None and _prose_date(fhlb) == [None] and _prose_date("**Update**" + fhlb[6:]) == [None]
    heloc = "Rates and introductory APR are accurate as of 3/1/26 and subject to change."
    achieve = ("As of, 8/24/26, the tiered introductory rate structure is as follows: $25,000.00-99,999.99 at 4.00% dividend rate "
               "and 3.66% APY.")
    assert (_date_of(heloc + "\n"), _prose_date(heloc)) == ("2026-03-01", ["2026-03-01"])
    assert (_date_of(achieve + "\n"), _prose_date(achieve)) == ("2026-08-24", ["2026-08-24"])
    for counted in ("1Rates are accurate as of 3/1/26.", "**Rates are accurate as of 3/1/26.**", "\\*Rates are accurate as of 3/1/26.",
                    "Our loan Rates are accurate as of 3/1/26.", "As of 3/1/26 at 3:00 PM CST, Rates are lower.",
                    "As of 3/1/26, the FHLB Mortgage Rate Relief rate is 3.00%."):
        assert _prose_date(counted) == ["2026-03-01"], counted  # sentence-initial, after a lowercase word or a comma, or lowercase
    for file in ("newsroom-brian-henneger-vp-mortgage-lending-a6200e.md",
                 "newsroom-dupaco-making-homeownership-more-affordable-with-special-fhlb-mortgage-rate-relie-54805a.md"):
        blocks = split_blocks(page("pages/" + file), load_boilerplate())
        fhlb_blocks = [b for b in blocks if any("FHLB Mortgage Rate Relief program have been allocated" in l for l in b.lines)]
        assert fhlb_blocks and all(b.effective_date is None for b in fhlb_blocks), file
    home_equity = Path("snapshots/01_2026-05-12_baseline/pages/personal-loans-home-equity-bb3422.md").read_text(encoding="utf-8")
    assert "2026-03-01" in [b.effective_date for b in split_blocks(home_equity, load_boilerplate()) if b.kind == "prose"]

def test_effective_date_is_the_nearest_after_the_cue_and_never_an_end_date():
    for ends in ("Rates effective immediately, offer valid through 12/31/2026.", "Rates effective immediately; offer valid through 12/31/2026.",
                 "Rates effective until 12/31/2026.", "Effective now; this offer expires 12/31/2026."):
        assert (_date_of(ends + "\n"), _prose_date(ends)) == (None, [None]), ends
    assert (_date_of("Rates are effective 09/01/2026.\n"), _prose_date("Rates are effective 09/01/2026.")) == ("2026-09-01", ["2026-09-01"])
    assert _date_of("Rates effective 09/01/2026, offer valid through 12/31/2026.\n") == "2026-09-01"  # the nearest date after the cue
    card = ("The 2.90% introductory APR expires six months from the date of your first balance transfer, at which time the APR "
            "will revert back to the current standard APR, which effective 1/1/2026 is a variable rate.")
    assert _prose_date(card) == ["2026-01-01"]  # an end word before the cue blocks nothing

def test_effective_beats_as_of_in_one_trailer_and_as_of_keeps_the_window_open():
    as_of, effective = "Rates and introductory APR are accurate as of 3/1/26.", "Rates effective 09/01/2026."
    for gap in ("\n", "\n\n"):  # adjacent lines, then a blank line between them
        assert _date_of(as_of + gap + effective + "\n") == "2026-09-01", repr(gap)
        (tbl,) = _tables("| Account Type | APY |\n| --- | --- |\n| Achieve Money Market | 3.25% |\n\n" + as_of + gap + effective + "\n")
        assert [l for l in tbl.lines if not l.startswith("|")] == [as_of, effective], repr(gap)
    assert _date_of(effective + "\n\n" + as_of + "\n") == "2026-09-01"  # a blank line after an effective line still ends the window
    assert _date_of(as_of + "\n\nSome unrelated prose.\n") == "2026-03-01"  # an as-of line alone still dates the table

def test_footnote_lines_never_caption_the_next_table():
    from kb.pagetype import segment_of
    table = "| Account Type | APY |\n| --- | --- |\n| {} | 0.50% |\n\n"
    def second(line): return _tables("## Savings\n" + table.format("Share Savings") + line + "\n\n" + table.format("Money Market"))[1]
    for note in ("\\*Business accounts are excluded from this offer", "*Business accounts are excluded",
                 "1Business accounts are excluded", "2 Business accounts are excluded", "3. Business accounts are excluded"):
        assert second(note).heading_path == ("Savings",), note
        assert segment_of("https://www.dupaco.com/rates", second(note).heading_path) == "personal", note
    for caption in ("Special Certificates", "1st Rate Checking"):
        assert second(caption).heading_path == ("Savings", caption)


# tests/test_10_extract.py  (section C)
from kb.extract_rules import extract_page, SourceContext
from kb.registry import Registry
CTX = SourceContext("https://www.dupaco.com/rates", "https://www.dupaco.com/rates", "rate_sheet", 3, "05_2026-09-28_latest", "2026-09-28T03:25:42.386Z")

def _facts(): return extract_page(page("pages/rates-59a9e6.md"), CTX, Registry.load(), load_boilerplate())
def _one(facts, pid, attr, **q):
    hits = [f for f in facts if f.product_id == pid and f.attribute == attr and all(dict(f.qualifiers).get(k) == v for k, v in q.items())]
    assert len(hits) == 1, hits; return hits[0]

def test_certificate_special_rows():
    f = _one(_facts(), "cert_special", "apy", term_months=17, jumbo=False)
    assert (f.value, f.value_text, f.effective_date) == (4.10, "4.10%", "2026-09-01") and "4.10%2" in f.source.quote
    assert _one(_facts(), "cert_special", "dividend_rate", term_months=17, jumbo=True).value == 4.15

def test_share_savings_tiers_and_auto_model_years():
    assert _one(_facts(), "share_savings", "apy", balance_min=10000.0, balance_max=24999.99).value == 0.15
    assert _one(_facts(), "share_savings", "apy", balance_min=25000.0, balance_max=None).value == 0.20
    f = _one(_facts(), "auto_loan", "apr", model_year_min=2024, model_year_max=2027, term_months=60)
    assert (f.value, f.value_text, f.effective_date) == (5.39, "5.39% APR", "2026-08-31")

def test_mortgage_amount_tiers_keep_rate_and_apr():
    assert _one(_facts(), "mortgage_purchase", "rate", term_months=360, loan_amount_max=100000.0).value == 7.13
    assert _one(_facts(), "mortgage_purchase", "apr", term_months=360, loan_amount_max=832750.0).value == 7.29

def test_calculator_copy_is_lower_authority_and_older():
    ctx = SourceContext("https://www.dupaco.com/calculators/vehicle-affordability", "https://www.dupaco.com/calculators/vehicle-affordability", "calculator", 1, "05_2026-09-28_latest", "2026-09-28T03:25:42.386Z")
    f = _one(extract_page(page("pages/calculators-vehicle-affordability-bc054b.md"), ctx, Registry.load(), load_boilerplate()), "auto_loan", "apr", model_year_min=2023, model_year_max=2026, term_months=60)
    assert f.value == 5.34 and f.source.authority == 1

def test_contact_facts():
    ctx = SourceContext("https://www.dupaco.com/contact", "https://www.dupaco.com/contact", "contact", 1, "05_2026-09-28_latest", "2026-09-28T03:25:42.386Z")
    facts = extract_page(page("pages/contact-c99539.md"), ctx, Registry.load(), load_boilerplate())
    assert _one(facts, "membership", "routing_number").value_text == "273974581"
    assert _one(facts, "membership", "reply_hours").value_text == "Monday–Friday, 8:30 a.m.–5:30 p.m."

def test_headerless_table_is_ignored_not_guessed():
    md = "| 5.19% APR | 48 Months |\n| 5.39% APR | 60 Months |\n"
    assert extract_page(md, CTX, Registry.load(), frozenset()) == []

from kb import extract_rules
from kb.normalize import canonical_url
from kb.types import ClaimType

def _extract(snapshot, url):
    snap = Path("snapshots") / snapshot
    man = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    p = next(p for p in man["pages"] if canonical_url(p["url"]) == url)
    md = (snap / p["file"]).read_text(encoding="utf-8")
    pt = classify(p["url"], md)
    return extract_page(md, SourceContext(p["url"], url, pt, authority_of(pt), man["snapshot_id"], p["fetched_at"]), Registry.load(), load_boilerplate())

def test_promotional_columns_carry_intro():
    facts = _extract("05_2026-09-28_latest", "https://www.dupaco.com/earn-more")
    tier = [(f.attribute, f.value, dict(f.qualifiers).get("intro")) for f in facts if f.product_id == "achieve_money_market" and f.attribute in ("dividend_rate", "apy")
            and dict(f.qualifiers).get("balance_min") == 25000.0 and dict(f.qualifiers).get("balance_max") == 99999.99]
    assert sorted(tier, key=repr) == sorted([("dividend_rate", 4.0, True), ("apy", 3.66, True), ("dividend_rate", 3.2, None), ("apy", 3.25, None)], key=repr)

def test_inline_pass_does_not_guess_a_mortgage_from_a_heloc_disclosure():
    facts = _extract("01_2026-05-12_baseline", "https://www.dupaco.com/rates")
    assert [f for f in facts if f.product_id == "mortgage_purchase" and f.confidence < 1.0] == []
    assert any(f.product_id == "platinum_visa" and f.confidence < 1.0 and dict(f.qualifiers).get("intro") is True for f in facts)

def test_contact_phone_and_branch_addresses():
    facts = _extract("05_2026-09-28_latest", "https://www.dupaco.com/contact")
    assert _one(facts, "membership", "phone").value_text == "800-373-7600"
    assert len([f for f in facts if (f.product_id, f.attribute) == ("branch", "address")]) == 6
    assert _one(facts, "branch", "address", branch_name="oldenburg ln., galena").value_text == "11375 Oldenburg Ln., Galena, IL, 61036"

def test_mortgage_row_points_payment_example_and_apr():
    facts, q = _facts(), {"term_months": 360, "loan_amount_max": 100000.0}
    points = _one(facts, "mortgage_purchase", "points", **q)
    assert points.value == 0 and points.claim_type == ClaimType.ASSERTION
    example = _one(facts, "mortgage_purchase", "payment_example", **q)
    assert example.value == 673.80 and example.unit == "usd"
    assert _one(facts, "mortgage_purchase", "apr", **q).value == 7.27

def test_card_rate_range_keeps_its_full_text():
    f = _one(_facts(), "platinum_visa", "apr", intro=False)
    assert f.value == 12.5 and f.value_text == "12.50% – 19.50%"

def test_unmapped_lists_only_never_seen_rows():
    extract_rules.reset_census()
    _facts()
    assert extract_rules.UNMAPPED == [] and extract_rules.IGNORED == 0
    _extract("05_2026-09-28_latest", "https://www.dupaco.com/calculators/vehicle-affordability")
    assert extract_rules.UNMAPPED == [] and extract_rules.IGNORED == 12  # its balance and payment-chart tables
    md = "## Mystery Accounts\n| Account Type | APY |\n| --- | --- |\n| Unicorn Savings | 1.00% |\n"
    assert extract_page(md, CTX, Registry.load(), frozenset()) == []
    assert extract_rules.UNMAPPED == [("https://www.dupaco.com/rates", ("Mystery Accounts",), "Unicorn Savings")]
    extract_rules.reset_census()
    assert extract_rules.UNMAPPED == [] and extract_rules.IGNORED == 0

def test_payment_examples_after_a_table_reach_the_inline_pass():
    for snapshot, url in (("01_2026-05-12_baseline", "https://www.dupaco.com/rates"),
                          ("04_2026-08-27_rebaseline", "https://www.dupaco.com/personal/loans/recreational-loans")):
        inline = {(f.product_id, f.attribute, f.value) for f in _extract(snapshot, url) if f.confidence < 1.0}
        assert {("boat_rv_loan", "apr", 7.09), ("atv_loan", "apr", 8.34)} <= inline, (snapshot, url)

def test_routing_number_on_every_page_that_states_it():
    f = _one(_extract("05_2026-09-28_latest", "https://www.dupaco.com/business/cash-management"), "membership", "routing_number")
    assert (f.value_text, f.source.quote) == ("273974581", "- Simple incoming: Receive funds by sharing our routing number (273974581) and your account info.")
    contact = _one(_extract("05_2026-09-28_latest", "https://www.dupaco.com/contact"), "membership", "routing_number")  # still one
    assert (contact.value_text, contact.source.quote) == ("273974581", "**Routing Number:** 273974581")
    def routing(md): return [(f.value_text, f.source.quote) for f in extract_page(md, CTX, Registry.load(), frozenset()) if f.attribute == "routing_number"]
    assert routing("Direct deposit is easy. You need our routing number (273974581) and your account number.\n") == [
        ("273974581", "You need our routing number (273974581) and your account number.")]  # a rate sheet too, quoted by its sentence
    assert routing("- **Our routing number:** Provide the payer with our ABA number (273974581).\n") == []  # words in between
    assert routing("Routing Number: 273974581\n\nRouting Number: 273974581\n") == [("273974581", "Routing Number: 273974581")]  # once a page

def test_footnote_rate_sentence_under_a_table_reaches_the_inline_pass():
    md = ("Boat & RV Loans\n\n| Loan Amount | Term | APR |\n| --- | --- | --- |\n| $40,000+ | 60 Months | 7.09% |\n\n"
          "\\*Boat & RV loan payment example: If you borrow $50,000 at a 7.09% annual percentage rate (APR) for 60 months, your payment is $992.45.\n"
          "Rates effective 01/01/2023.\n")
    inline = [f for f in extract_page(md, CTX, Registry.load(), frozenset()) if f.confidence < 1.0]
    assert [(f.product_id, f.attribute, f.value, f.effective_date) for f in inline] == [("boat_rv_loan", "apr", 7.09, None)]
