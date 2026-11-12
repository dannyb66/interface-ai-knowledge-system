from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_coverage_report import matrix


def requirement(**changes):
    return {"entity": "program", "attribute": "eligibility", "claim_set": "requirements",
            "crawls": ["old", "new"], "required_claim_ids": ["purchase", "threshold"], **changes}


def test_attribute_presence_does_not_count_as_complete_eligibility():
    available = {("program", "eligibility", "old"): {"purchase"},
                 ("program", "eligibility", "new"): {"purchase", "threshold"}}
    rows = matrix([requirement()], available)
    assert [(r["crawl"], r["complete"]) for r in rows] == [("new", True), ("old", False)]
    assert rows[1]["missing_claim_ids"] == ["threshold"]


def test_quarantined_group_stays_incomplete_even_if_quotes_are_present():
    rows = matrix([requirement(crawls=["new"], disposition="quarantined")],
                  {("program", "eligibility", "new"): {"purchase", "threshold"}})
    assert not rows[0]["complete"]


def test_other_attributes_and_crawls_cannot_rescue_missing_required_claim():
    rows = matrix([requirement(crawls=["new"])], {("program", "description", "new"): {"purchase", "threshold"},
                  ("program", "eligibility", "old"): {"purchase", "threshold"}})
    assert rows[0]["verified_claim_ids"] == []


@pytest.mark.parametrize("required", [[], ["purchase", "purchase"], [""], ["   "]])
def test_empty_or_duplicated_required_set_is_not_success(required):
    with pytest.raises(ValueError):
        matrix([requirement(required_claim_ids=required)], {})
