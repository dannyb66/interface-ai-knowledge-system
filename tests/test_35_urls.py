# tests/test_35_urls.py
"""Gate fix item 1: url facts from product pages, the contact page and the /about/join link."""
import json
from pathlib import Path

import pytest
from scoring import contains, score_item

from kb.blocks import load_boilerplate
from kb.compose import render_with_dropped, strip_residue
from kb.extract_rules import SourceContext, extract_page
from kb.normalize import canonical_url
from kb.pagetype import authority_of, classify
from kb.question import parse
from kb.registry import Registry
from kb.resolve import resolve
from kb.tiers import current
from kb.types import AnswerPlan

SITE = "https://www.dupaco.com"
FIRST, LATEST = "01_2026-05-12_baseline", "05_2026-09-28_latest"


def _page_facts(snapshot, url):
    """``extract_page`` of the first page of ``snapshot`` whose canonical URL is ``url``, typed as ``classify`` does."""
    snap = Path("snapshots") / snapshot
    man = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    p = next(p for p in man["pages"] if canonical_url(p["url"]) == url)
    md = (snap / p["file"]).read_text(encoding="utf-8")
    pt = classify(p["url"], md)
    ctx = SourceContext(p["url"], url, pt, authority_of(pt), man["snapshot_id"], p["fetched_at"])
    return extract_page(md, ctx, Registry.load(), load_boilerplate())


def _urls(facts, pid=None):
    return [(f.product_id, f.value_text) for f in facts if f.attribute == "url" and pid in (None, f.product_id)]


def _winner(store, snapshot, pid):
    """The url the resolver answers for ``pid`` in ``snapshot``: one fact per key, in store rank."""
    facts = current(store.in_force(snapshot, pid, "url", None))
    return facts[0].value_text if facts else None


def _url_facts(store):
    return [f for index in store.by_product_attr.values() for (_, attr), facts in sorted(index.items()) if attr == "url"
            for f in facts]


@pytest.mark.parametrize("qid", ["dup-008", "dup-080", "dup-082"])
def test_public_url_items_answer_with_the_link_and_its_source(ks_full, public_items, qid):
    item = next(it for it in public_items if it["id"] == qid)
    answer = ks_full.answer(item["question"], item.get("as_of"))
    result = score_item(item, answer)
    assert answer.confident and result["score"] == 1.0 and not result["trap_hits"], (answer.text, result)


def test_dup_008_resolves_to_the_regular_certificates_page(ks_full, public_items):
    question = next(it["question"] for it in public_items if it["id"] == "dup-008")
    q = parse(question, None, ks_full.registry)
    plan = resolve(q, ks_full.store, ks_full.registry)
    assert (q.intent, q.product_id, q.attribute) == ("url", "cert_regular", "url")
    assert [f.value_text for f in plan.facts] == [SITE + "/personal/savings-account"]
    assert [s.canonical_url for s in plan.sources] == [SITE + "/personal/savings-account"]


# The latest crawl: one product of each family that gets a url fact, and the page the resolver answers with.
HOMES = {"share_savings": "/personal/savings-account", "money_market_investors_choice": "/personal/savings-account",
         "cert_regular": "/personal/savings-account", "ira_cert": "/personal/retirement",
         "first_rate_checking": "/personal/checking-accounts", "auto_loan": "/personal/loans/auto-motorcycle-loans",
         "boat_rv_loan": "/personal/loans/recreational-loans", "mortgage_purchase": "/personal/loans/home-loans",
         "heloc": "/personal/loans/home-equity", "business_platinum_visa": "/business/credit-cards",
         "business_savings": "/business/savings-accounts", "business_checking": "/business/checking-accounts"}


def test_each_family_links_to_its_product_page(store_full):
    assert {pid: _winner(store_full, LATEST, pid) for pid in HOMES} == {pid: SITE + path for pid, path in HOMES.items()}


def test_a_product_page_names_each_product_once_with_its_own_url():
    facts = _page_facts(LATEST, SITE + "/personal/savings-account")
    urls = _urls(facts)
    assert len(urls) == len(set(urls)) and {url for _, url in urls} == {SITE + "/personal/savings-account"}
    assert {pid for pid, _ in urls} == {f.product_id for f in facts if f.attribute in ("apy", "dividend_rate")}
    cert = next(f for f in facts if (f.product_id, f.attribute) == ("cert_regular", "url"))
    assert (cert.qualifiers, cert.unit, cert.value, cert.source.quote) == ((), "text", None, "Regular Certificates")


def test_rate_sheets_name_no_url(store_full):
    for snapshot in (FIRST, LATEST):
        for path in ("/rates", "/business-rates"):
            facts = _page_facts(snapshot, SITE + path)
            assert facts and _urls(facts) == [], (snapshot, path)  # the page has rows, but no url
    assert {f.source.page_type for f in _url_facts(store_full)} == {"product_page", "contact", "about", "rate_sheet", "legacy_alias"}  # A19: own-page facts


def test_the_rate_sheet_widget_on_a_product_page_names_no_url(store_full):
    # Crawls 01-04 embed the rate sheet's tab widget ("Rates > Select an option below:") on the checking page.
    facts = _page_facts(FIRST, SITE + "/personal/checking-accounts")
    assert {"auto_loan", "platinum_visa", "personal_loan", "home_equity"} <= {f.product_id for f in facts}
    assert _urls(facts) == []
    assert _winner(store_full, FIRST, "platinum_visa") == SITE + "/personal/credit-cards"
    assert _winner(store_full, FIRST, "personal_loan") == SITE + "/personal/loans/personal-loans"
    assert _winner(store_full, FIRST, "home_equity") == SITE + "/personal/loans/home-equity"
    assert _winner(store_full, FIRST, "home_improvement_loan") is None  # A19: own page absent from the first crawl


def test_contact_page_is_the_branch_locator_link():
    facts = _page_facts(LATEST, SITE + "/contact")
    assert _urls(facts) == [("branch", SITE + "/contact")]
    assert next(f for f in facts if f.attribute == "url").source.quote == "Find a Location Near You"


def test_join_link_comes_only_from_the_join_page():
    facts = _page_facts(LATEST, SITE + "/about/join")
    assert _urls(facts) == [("membership", "https://join.dupaco.com/")]
    assert next(f for f in facts if f.attribute == "url").source.quote == "[Become a member](https://join.dupaco.com/)"
    # The home page's "Join Dupaco" points at /about/join; the savings page links join.dupaco.com/product/...
    for url in (SITE, SITE + "/personal/savings-account"):
        assert _urls(_page_facts(LATEST, url), "membership") == [], url
    md = "[Continue my application](https://join.dupaco.com/login)\n\n[Join Dupaco](https://join.dupaco.com/)\n"
    for url, want in ((SITE + "/about/join", [("membership", "https://join.dupaco.com/")]), (SITE + "/about", [])):
        ctx = SourceContext(url, url, "about", 1, LATEST, "2026-09-28T03:14:45.391Z")
        assert _urls(extract_page(md, ctx, Registry.load(), frozenset())) == want, url


def test_no_url_holds_a_trap_token_and_every_url_renders_byte_for_byte(store_full):
    items = [json.loads(line) for name in ("public_eval.jsonl", "dev_extra.jsonl")
             for line in (Path("eval") / name).read_text().splitlines() if line.strip()]
    traps = sorted({t for it in items for t in it.get("must_not_include", [])})
    facts = _url_facts(store_full)
    urls = sorted({f.value_text for f in facts})
    assert "https://join.dupaco.com/" in urls and SITE + "/contact" in urls
    assert [(u, t) for u in urls for t in traps + ["info.dupaco.com", "/locations/branch-hours"] if contains(u, t)] == []
    for f in [next(g for g in facts if g.value_text == url) for url in urls]:  # every distinct url once
        assert strip_residue(f.value_text) == f.value_text
        for intent, head in (("url", None), ("how_to", "You can do that online at ")):
            plan = AnswerPlan(intent, (f,), frozenset(), (f.source,), True, None, f.source.snapshot_id)
            text = render_with_dropped(plan)[0].text
            assert text.endswith(" " + f.value_text) and (head is None or text == head + f.value_text), text
