"""Independent sealed-holdout checks; diagnostics expose aggregate counts only."""
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "eval" / "proxy"
SUPPORTED_FAMILIES = frozenset({
    "rate_current", "rate_as_of", "rate_change", "tier_amount",
    "refuse_unpublished", "hours_branch", "hours_day", "closure",
    "count", "count_year", "contested_day",
})


def _load_jsonl(path):
    rows = []
    invalid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if not isinstance(value, dict):
            invalid += 1
            continue
        rows.append(value)
    if invalid:
        raise AssertionError("Invalid JSONL row count: %d" % invalid)
    return rows


def _normalize(question):
    text = unicodedata.normalize("NFKC", question).casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def _question_metrics(holdout, proxy):
    # Never put individual questions or template text in a failure diagnostic.
    malformed = sum(not isinstance(row.get("question"), str) for row in holdout + proxy)
    if malformed:
        return malformed, 0, 0
    public_normalized = {_normalize(row["question"]) for row in proxy}
    public_tokens = [frozenset(value.split()) for value in public_normalized]
    exact = near = 0
    for row in holdout:
        question = _normalize(row["question"])
        tokens = frozenset(question.split())
        exact += question in public_normalized
        if tokens:
            near += any(
                len(tokens & other) / len(tokens | other) > 0.8
                for other in public_tokens
            )
    return malformed, exact, near


class HoldoutIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.holdout = _load_jsonl(PROXY / "holdout.jsonl")
        cls.proxy = _load_jsonl(PROXY / "proxy.jsonl")
        cls.templates = json.loads((PROXY / "holdout_templates.json").read_text(encoding="utf-8"))

    def test_at_least_120_items(self):
        count = len(self.holdout)
        self.assertGreaterEqual(count, 120, "Holdout item count: %d" % count)

    def test_item_ids_are_unique_and_prefixed(self):
        ids = [row.get("id") for row in self.holdout]
        malformed = sum(not isinstance(item_id, str) or not item_id.startswith("h-") for item_id in ids)
        duplicate = sum(count - 1 for count in Counter(ids).values() if count > 1)
        self.assertEqual(malformed, 0, "Invalid holdout ID count: %d" % malformed)
        self.assertEqual(duplicate, 0, "Duplicate holdout ID count: %d" % duplicate)

    def test_ids_are_distinct_from_proxy(self):
        overlap = len({row.get("id") for row in self.holdout} & {row.get("id") for row in self.proxy})
        self.assertEqual(overlap, 0, "Overlapping ID count: %d" % overlap)

    def test_questions_are_independent_from_proxy(self):
        malformed, exact, near = _question_metrics(self.holdout, self.proxy)
        self.assertEqual(malformed, 0, "Invalid question count: %d" % malformed)
        self.assertEqual(exact, 0, "Normalized exact overlap count: %d" % exact)
        self.assertEqual(near, 0, "Token Jaccard above 0.8 count: %d" % near)

    def test_each_supported_family_has_three_independent_templates(self):
        families = self.templates.get("families", {})
        missing = len(SUPPORTED_FAMILIES - families.keys())
        short = sum(len(spec.get("templates", [])) < 3 for spec in families.values())
        templates = [template for spec in families.values() for template in spec.get("templates", [])]
        invalid_ids = sum(not str(template.get("id", "")).startswith("h-") for template in templates)
        duplicate_ids = len(templates) - len({template.get("id") for template in templates})
        duplicate_wording = sum(
            len(spec.get("templates", [])) - len({_normalize(template["text"]) for template in spec.get("templates", [])})
            for spec in families.values()
        )
        self.assertEqual(missing, 0, "Missing family count: %d" % missing)
        self.assertEqual(short, 0, "Families below three templates: %d" % short)
        self.assertEqual(invalid_ids, 0, "Invalid template ID count: %d" % invalid_ids)
        self.assertEqual(duplicate_ids, 0, "Duplicate template ID count: %d" % duplicate_ids)
        self.assertEqual(duplicate_wording, 0, "Repeated template wording count: %d" % duplicate_wording)


if __name__ == "__main__":
    unittest.main()
