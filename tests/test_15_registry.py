# tests/test_15_registry.py
import copy
import json
from pathlib import Path
import pytest
from kb.config import DEFAULT_DATA_DIR
from kb.registry import Registry
from kb.blocks import split_blocks, load_boilerplate, table_rows
from kb.normalize import canonical_url
from kb.pagetype import segment_of

def test_resolve_known_labels():
    r = Registry.load()
    res = r.resolve("https://www.dupaco.com/rates", ("Special Certificates",), "17 Month Fixed Jumbo Certificate Special", "personal")
    assert res.product_id == "cert_special" and res.qualifiers == {"term_months": 17, "jumbo": True, "special": True}
    res = r.resolve("https://www.dupaco.com/rates", ("Auto Loans",), "2024-27 Model Year", "personal")
    assert res.product_id == "auto_loan" and res.qualifiers == {"model_year_min": 2024, "model_year_max": 2027}

def test_display_name_is_the_first_name():
    r = Registry.load()
    assert (r.display_name("first_rate_checking"), r.display_name("business_checking")) == ("1st Rate Checking", "Business 1st Rate Checking")
    with pytest.raises(KeyError): r.display_name("jump_start_savings")

def test_registry_covers_all_snapshots():
    r = Registry.load(); unmapped = []; scanned = 0
    for snap in sorted(Path("snapshots").glob("0*_*")):
        man = json.loads((snap / "manifest.json").read_text())
        for p in man["pages"]:
            md = (snap / p["file"]).read_text(encoding="utf-8")
            for b in split_blocks(md, load_boilerplate()):
                if b.kind != "table": continue
                cu = canonical_url(p["url"])
                for row in table_rows(b):
                    scanned += 1  # empty labels too: the extractor resolves them by section ("^$" rules)
                    if r.resolve(cu, b.heading_path, row.label or "", segment_of(cu, b.heading_path)) is None:
                        unmapped.append((snap.name, p["url"], b.heading_path, row.label))
    assert scanned > 2000, "only {} table rows scanned; are the snapshots unpacked under snapshots/?".format(scanned)
    assert unmapped == []

def test_null_required_qualifier_needs_allowlist(tmp_path):
    data = json.loads((DEFAULT_DATA_DIR / "products.json").read_text(encoding="utf-8"))
    assert [x["product_id"] for x in data["label_rules"] if "allow_null" in x] == ["mortgage_rate_relief"]
    mutations = (lambda d: next(x for x in d["label_rules"] if "allow_null" in x).pop("allow_null"),
                 lambda d: next(x for x in d["label_rules"] if x["product_id"] == "auto_loan")["qualifiers"].update(model_year_min=None))
    for mutate in mutations:
        bad = copy.deepcopy(data); mutate(bad)
        path = tmp_path / "products.json"; path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="is null but the rule's allow_null does not list it"):
            Registry.load(path)
