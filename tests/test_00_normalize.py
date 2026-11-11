# tests/test_00_normalize.py
import re
from kb import normalize as n
from scoring import _numbers, _norm

def test_strip_footnote_cells():
    assert n.strip_footnote("4.10%2") == "4.10%" and n.strip_footnote("5.39% APR1") == "5.39% APR"
    assert n.strip_footnote("Annual Percentage Yield (APY)1") == "Annual Percentage Yield (APY)" and n.strip_footnote("$1,000.00") == "$1,000.00"

def test_strip_footnote_spaced_markers():
    assert n.strip_footnote("15.50% 1") == "15.50%" and n.strip_footnote("20.5% 1") == "20.5%"
    assert n.strip_footnote("5.39% APR 1") == "5.39% APR" and n.strip_footnote("4.00% APY 2") == "4.00% APY"
    assert n.strip_footnote("$1,000.00") == "$1,000.00" and n.strip_footnote("12.50% – 19.50%2") == "12.50% – 19.50%"

def test_tiers_terms_and_model_years():
    assert n.parse_tier("$25,000+") == (25000.0, None) and n.parse_tier("$832750 or less") == (None, 832750.0)
    assert n.parse_tier("$10,000 – $24,999.99") == (10000.0, 24999.99)
    assert n.parse_term_months("30-Year") == 360 and n.parse_term_months("17 Month Fixed Jumbo Certificate Special") == 17 and n.parse_term_months("(60 mo)") == 60
    assert n.parse_model_years("2023–26 Model Year") == (2023, 2026) and n.parse_model_years("2016 Model Year (and older)") == (0, 2016)

def test_dates_and_as_of():
    assert n.parse_date("Rates are effective as of 09/01/2026 and") == "2026-09-01" and n.parse_date("08/13/25") == "2025-08-13"
    assert n.parse_date("June 20, 2025") == "2025-06-20" and n.parse_date("Effective February 17, 2025") == "2025-02-17"
    assert n.parse_as_of("2026-05-31") == "2026-05-31" and n.parse_as_of("May 2026") == "2026-05-31" and n.parse_as_of("not-a-date") is None

def test_canonical_url():
    assert n.canonical_url("https://www.dupaco.com/personal/loans/auto-loans/?hsLang=en#rates") == "https://www.dupaco.com/personal/loans/auto-loans"

def test_number_tokens_parity_with_scorer():
    for s in ("4.10% APY ($1,000 minimum)", "7.13% rate / 7.27% APR", "273974581", "8:30 a.m.–5:30 p.m.", "$832,750 or less"):
        assert n.number_tokens(s) == _numbers(s)
    assert n.norm_text("8:30 a.m.–5:30 p.m.") == _norm("8:30 a.m.–5:30 p.m.")

def test_scorer_norm_is_verbatim_scorer_norm():
    for s in ("Dupaco’s “New Money”", "24‑hour ATM", "8:30 a.m.–5:30 p.m."):
        assert n.scorer_norm(s) == _norm(s)
