# tests/test_05_types.py
import dataclasses, json, pytest
from kb.types import ClaimType, Fact, Source, make_key, fact_to_dict, fact_from_dict

def _fact():
    src = Source("https://www.dupaco.com/rates", "https://www.dupaco.com/rates", "rate_sheet", 3, "05_2026-09-28_latest", "2026-09-28T03:25:42.386Z", 7, 1, "| 17 Month Fixed Certificate Special | 4.06% | 4.10%2 | $1,000.00 |")
    key = make_key("cert_special", "apy", {"term_months": 17, "jumbo": False, "special": True, "segment": "personal", "day": None})
    return Fact(key, "cert_special", "apy", key[2], 4.10, "4.10%", "pct", ClaimType.RATE, "2026-09-01", None, None, src, "rules", 1.0)

def test_key_is_sorted_and_drops_none():
    assert make_key("a", "b", {"z": 1, "m": None, "a": 2}) == ("a", "b", (("a", 2), ("z", 1)))

def test_fact_is_frozen_and_hashable():
    f = _fact()
    with pytest.raises(dataclasses.FrozenInstanceError): f.value = 1.0
    assert hash(f) == hash(_fact())

def test_fact_round_trips_through_json():
    f = _fact()
    assert fact_from_dict(json.loads(json.dumps(fact_to_dict(f)))) == f
