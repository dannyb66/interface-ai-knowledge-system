"""Audited sentence choices; print provenance-expanded JSON, never overwrite curated data."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
from kb.normalize import canonical_url
from kb.verify import page_text, quote_found

# Sentences read in the named product's own heading or card. Expansion only finds exact copies.
DESCRIPTIONS = [
    ("share_savings", "Whether you’re tucking away money for a rainy day or naming your specific dreams, our primary savings account is your ticket to ownership and member perks."),
    ("bright_savings", "With no monthly service fees or minimums to hold you back, it’s easier to grow your money with this online-only account."),
    ("holiday_club_savings", "Make your holiday season brighter by saving year-round."),
    ("high_yield_savings", "We offer three options—Investor’s Choice, Achieve and High-Yield Savings—so you can choose the best fit for your balance and goals."),
    ("money_market_investors_choice", "We offer three options—Investor’s Choice, Achieve and High-Yield Savings—so you can choose the best fit for your balance and goals."),
    ("achieve_money_market", "We offer three options—Investor’s Choice, Achieve and High-Yield Savings—so you can choose the best fit for your balance and goals."),
    ("hsa", "If you have a high-deductible health plan, an HSA is a smart way to save for medical expenses with potential tax advantages"),
    ("launchpad_savings", "This account helps you build your retirement fund one small step at a time if you aren’t ready to invest in a retirement account or don’t have a 401(k) at work."),
    ("first_rate_checking", "This account pays dividends on the money you keep in checking—without requiring a certain number of debit transactions."),
    ("free_checking", "No monthly fees, no minimum balance and no hoops to jump through—just a straightforward place to manage your everyday spending."),
    ("cert_regular", "Certificates (the credit union version of bank CDs) provide a deliberate approach to saving—whether you’re planning for a big purchase or just want a secure place to grow your money."),
    ("cert_special", "Certificates (the credit union version of bank CDs) provide a deliberate approach to saving—whether you’re planning for a big purchase or just want a secure place to grow your money."),
    ("auto_loan", "Whether you're buying a car, truck, or motorcycle, getting the right financing should feel just as smooth as the drive."),
    ("atv_loan", "From water to trails, Dupaco makes financing boats, RVs, ATVs, jet skis and snowmobiles simple."),
    ("boat_rv_loan", "From water to trails, Dupaco makes financing boats, RVs, ATVs, jet skis and snowmobiles simple."),
    ("personal_loan", "From covering an unexpected expense to tackling a passion project, Dupaco’s personal loans are here to help."),
    ("student_loans", "Whether you need to fill the funding gap for college or simplify repayment after graduation, we have flexible options to help you take your education higher."),
    ("mortgage_purchase", "Whether you’re buying your first home, refinancing or weighing your next move, we’ll help you find what fits your life—so you can move forward with confidence."),
    ("mortgage_refi", "See how adjusting your rate or payment could help you reach your financial goals."),
    ("construction_loan", "Get the support you need to finance your lot, construction and every step between."),
    ("home_improvement_loan", "Find the right way to fund your upgrades and make your current home even better."),
    ("cash_out_refi", "Replace your mortgage with a new one—and turn part of your equity into cash to use now."),
    ("heloc", "Borrow what you need, when you need it, with flexible access to your home's equity."),
    ("home_equity", "Apply for a one-time payout with fixed payments."),
    ("platinum_visa", "Best for keeping borrowing costs lower when you carry a balance or have larger expenses—simple, predictable and easy to manage."),
    ("rewards_visa", "Best for earning a little something back on what you're already buying—with simple, steady rewards that work in the background."),
    ("business_platinum_visa", "A reliable option for everyday business purchases."),
    ("business_rewards_visa", "Get cash back or other rewards on everyday business purchases."),
    ("business_checking", "Built for growing businesses that carry larger balances and prefer fewer extras."),
    ("business_savings", "Whether you’re planning for new equipment or setting aside funds for unexpected bills, our Business Share Savings and You-Name-It Savings accounts offer a flexible, cost-effective way to build reserves for your business."),
    ("business_you_name_it_savings", "Whether you’re planning for new equipment or setting aside funds for unexpected bills, our Business Share Savings and You-Name-It Savings accounts offer a flexible, cost-effective way to build reserves for your business."),
    ("business_high_yield_savings", "Our Investor's Choice and High-Yield Savings accounts offer flexible access to your funds while offering higher returns."),
    ("business_money_market", "Our Investor's Choice and High-Yield Savings accounts offer flexible access to your funds while offering higher returns."),
    ("business_cert_special", "Whether you choose our special or regular certificates, you’ll give your business a financial boost when you commit to saving for a set period."),
    ("business_cert_regular", "Whether you choose our special or regular certificates, you’ll give your business a financial boost when you commit to saving for a set period."),
    ("mobile_wallet", "Your Dupaco debit and credit cards are compatible with Apple Pay, Google Pay and Samsung Pay."),
]


def all_pages(normalized=True):
    result = {}
    for directory in sorted((ROOT / "snapshots").iterdir()):
        if not (directory / "manifest.json").is_file():
            continue
        meta = json.loads((directory / "manifest.json").read_text())
        result[meta["snapshot_id"]] = {canonical_url(p["url"]):
            (page_text((directory / p["file"]).read_text()) if normalized else (directory / p["file"]).read_text())
            for p in meta["pages"]}
    return result


def catalog():
    pages, entries = all_pages(), []
    def add(pid, attr, quote, item=None, published=None, value=None, unit="text", value_text=None, indices=None):
        matches = {sid: sorted(url for url, text in crawl.items() if quote_found(quote, text))
                   for sid, crawl in pages.items() if indices is None or int(sid[:2]) in indices}
        matches = {sid: urls for sid, urls in matches.items() if urls}
        if not matches:
            raise ValueError("no source for " + pid + ": " + quote)
        groups = {}
        for sid, urls in sorted(matches.items()):
            groups.setdefault(tuple(urls), []).append(sid)
        for urls, crawls in groups.items():
            entries.append(dict(canonical_urls=list(urls), crawls=crawls, quote=quote, product_id=pid,
                                attribute=attr, qualifiers={} if item is None else {"item": item}, value=value,
                                value_text=value_text or quote, unit=unit, claim_type="assertion", published_date=published,
                                event_date=None, extractor="curated"))
    for pid, quote in DESCRIPTIONS:
        add(pid, "description", quote)
    add("membership", "eligibility", "You live or work within our charter area or have an immediate family member who’s a member.", 1, indices=(1, 2, 3))
    for item, quote in enumerate(("You live or work within our charter area.", "You have an immediate family member who’s a member.", "You belong to the Rural Ideas Network."), 1):
        add("membership", "eligibility", quote, item, indices=(4, 5))
    add("membership", "eligibility", "You can find us in Iowa, Illinois and Wisconsin.", 2, indices=(1, 2, 3))
    add("membership", "eligibility", "You can find us in Iowa, Illinois and Wisconsin.", 4, indices=(4, 5))
    add("forbes_recognition", "description", "It was the fourth time Forbes recognized Dupaco.", published="2023-07-18")
    add("forbes_recognition", "description", "This was the fifth time Forbes recognized Dupaco.", published="2024-06-18")
    add("home_start", "description", "This initiative provides up to $15,000 in assistance, applied as a credit toward down payment and closing costs for eligible buyers beginning their homeownership journey.", published="2026-01-05")
    add("home_start", "eligibility", "Dubuque, Iowa—Dupaco Credit Union is partnering with the Federal Home Loan Bank (FHLB) of Des Moines to help first-time homebuyers take the leap into homeownership through the Home$tart program.", published="2026-01-05")
    add("mortgage_rate_relief", "eligibility", "The Mortgage Rate Relief program is available for eligible homebuyers, regardless of their location, and can only be applied to a new purchase.", published="2025-03-03")
    quote = "Enjoy face-to-face access and service at more than 5,600 participating credit unions nationwide."
    add("shared_branching", "count", quote, value=5600, unit="count", value_text="more than 5,600 participating credit unions")
    add("shared_branching", "description", quote)
    return {"_version": "2026-11-10 curated prose facts v1", "facts": entries}


if __name__ == "__main__":
    data = catalog()
    print('{"_version": ' + json.dumps(data["_version"]) + ', "facts": [')
    print(",\n".join(json.dumps(e, ensure_ascii=False) for e in data["facts"]))
    print("]}")
