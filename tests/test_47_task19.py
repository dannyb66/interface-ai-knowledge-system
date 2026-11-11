from pathlib import Path
import json
from scoring import score_item
from kb.question import parse
from kb.registry import Registry
from kb.temporal import select_dated
R = Registry.load()
S01, S05 = "01_2026-05-12_baseline", "05_2026-09-28_latest"
def _facts(store, sid, attr): return store.by_product_attr[sid].get(("branch", attr), [])
def _route(q, as_of=None):
    p = parse(q, as_of, R)
    return p.intent, p.product_id, p.attribute
def _item(items, i): return next(it for it in items if it["id"] == i)
def _score(ks, it): return score_item(it, ks.answer(it["question"], it.get("as_of")))["score"]
# tests/test_35_urls.py (append)
def test_page_overrides_and_page_level_links(ks_full):
    want = {"What's the link for home improvement loans?": "https://www.dupaco.com/personal/loans/home-improvement-loan",
            "What's the link for the Platinum Visa?": "https://www.dupaco.com/personal/credit-cards",
            "What's the URL for student loans?": "https://www.dupaco.com/personal/loans/student-loans",
            "What's the URL to contact Dupaco?": "https://www.dupaco.com/contact",
            "What's Dupaco's rates page?": "https://www.dupaco.com/rates",
            "What's Dupaco's website?": "https://www.dupaco.com"}
    for q, url in want.items():
        a = ks_full.answer(q)
        assert a.confident and url in a.text.split(), (q, a.text)  # render_url prints "{label}: {url}"

def test_value_questions_about_a_page(ks_full):
    assert "10.49%" in ks_full.answer("What does the web page say about the 36-month personal loan APR?").text  # (pin)
    assert "4.10%" in ks_full.answer("What does Dupaco's website say the 17-month certificate special pays?").text  # (pin)
    t = ks_full.answer("Is the 17-month certificate special listed on the website?").text
    assert t.startswith("Yes.") and "4.10%" in t  # (pin)
    assert "800-373-7600" in ks_full.answer("What phone number is on the website?").text  # (pin)
    assert "dupaco.com/personal/savings-account" in ks_full.answer("Which page lists the CD rates?").text  # (pin)
    assert "join.dupaco.com" in ks_full.answer("Can I become a member of Dupaco online?").text

def test_stale_url_question_says_no_without_echoing_it(ks_full):
    t = ks_full.answer("Is https://info.dupaco.com/certificate_account_rates still the page for certificate rates?").text
    assert t.startswith("No.") and "dupaco.com/personal/savings-account" in t and "info.dupaco.com" not in t
