"""Prose builder checks. Blind items are read only for aggregate metadata assertions."""
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from proxy_kit import Ctx, in_split
from proxy_prose import eligibility_scopes, kind_prose, recognition_claims

FAMILIES = {"description", "eligibility", "recognition", "fee"}


def test_both_splits_have_all_prose_families_and_disjoint_claims():
    metadata = {}
    for split in ("proxy", "holdout"):
        rows = [json.loads(line) for line in Path("eval/proxy/{}.jsonl".format(split)).read_text().splitlines()]
        metadata[split] = {(r["family"], r["key"]) for r in rows if r["family"] in FAMILIES}
        assert FAMILIES <= {family for family, _ in metadata[split]}
        for family in FAMILIES:
            assert len({r["template"] for r in rows if r["family"] == family}) >= 3, family
        for row in rows:
            if row["family"] in ("description", "fee"):
                assert in_split(ast.literal_eval(row["key"]), split)
    assert not metadata["proxy"] & metadata["holdout"]


def test_small_family_partition_is_fixed_before_scoring(store_full):
    pairs = json.loads(Path("eval/proxy/universe.json").read_text())["eligibility"]
    scopes = eligibility_scopes(pairs)
    assert set(scopes.values()) == {"proxy", "holdout"}
    assert scopes == eligibility_scopes(list(reversed(pairs)))
    facts = store_full.by_product_attr[store_full.snapshots()[-1][0]][("forbes_recognition", "description")]
    assert recognition_claims(facts) == [("2023-07-18", "proxy"), ("2024-06-18", "holdout")]
    spec = {"category": "stale_trap", "intent": "value", "templates": [{"id": "synthetic", "text": "Describe {product}."}]}
    proxy, holdout = [kind_prose(Ctx(store_full, split, {}), "recognition", spec, [("forbes_recognition", "description")])[0]
                      for split in ("proxy", "holdout")]
    assert proxy["as_of"] == "2023-07-18" and "fourth" in proxy["must_include"][0]
    assert holdout["as_of"] is None and "fifth" in holdout["must_include"][0]
    assert proxy["key"] != holdout["key"]


def test_eligibility_grades_every_applicable_sentence(store_full):
    pairs = json.loads(Path("eval/proxy/universe.json").read_text())["eligibility"]
    spec = {"category": "conflict_resolution", "intent": "value", "templates": [{"id": "synthetic", "text": "Who is eligible for {product}?"}]}
    rows = [item for split in ("proxy", "holdout") for item in kind_prose(Ctx(store_full, split, {}), "eligibility", spec, pairs)]
    membership = next(r for r in rows if r["route"][1] == "membership")
    complete = " ".join(membership["must_include"])
    for condition in ("Any", "live or work", "immediate family member", "Rural Ideas Network",
                      "open a savings account with $25", "keep at least $25", "Iowa, Illinois and Wisconsin"):
        assert condition in complete
    assert membership["must_not_include"] and all(t not in membership["must_include"] for t in membership["must_not_include"])
    assert len({r["key"] for r in rows}) == len(pairs)


def test_prose_template_contract():
    from build_proxy_set import check_templates
    spec = {"kind": "prose", "category": "entity_attribution", "intent": "value",
            "templates": [{"id": "p-unit", "text": "Describe {product}."}]}
    assert check_templates({"families": {"description": spec}}, "proxy") == []
