"""Present a verified schedule footnote only with its scoped, cited companion."""
from __future__ import annotations

import re
from .conditions import CONDITION_VALUES
from .verify import page_text

_TAX = "Sales tax may apply."
_SCOPE_WORDS = {
    "membership": {"member": "for members", "non_member": "for non-members"},
    "deposit_disposition": {"deposited": "with the coins deposited", "not_deposited": "when the coins are not deposited"},
    "statement_delivery": {"e_statements": "with e-statements", "without_e_statements": "without e-statements"},
    "usage_allowance": {"within_eight_free": "within the first eight free uses", "after_eight_free": "after the first eight free uses"},
    "card": {"debit": "for debit cards", "credit": "for credit cards"},
}


def scope_label(fact):
    if fact.attribute != "fee":
        return ""
    qualifiers = dict(fact.qualifiers)
    return "; ".join(values[qualifiers[key]] for key, values in _SCOPE_WORDS.items() if key in qualifiers)


def scope_survives(text, facts):
    return all(not scope_label(fact) or scope_label(fact) in page_text(text) for fact in facts)


def is_tax(fact):
    return (fact.attribute == "fee" and fact.semantics is not None
            and page_text(fact.value_text).lstrip("* ") == _TAX)


def same_scope(left, right):
    return (left.product_id == right.product_id and left.semantics is not None and right.semantics is not None
            and left.semantics.condition_group == right.semantics.condition_group
            and left.source.snapshot_id == right.source.snapshot_id
            and left.source.canonical_url == right.source.canonical_url
            and left.source.content_sha256 is not None
            and left.source.content_sha256 == right.source.content_sha256
            and {k: v for k, v in left.qualifiers if k in CONDITION_VALUES}
            == {k: v for k, v in right.qualifiers if k in CONDITION_VALUES})


def retain_scoped_companions(facts):
    return [fact for fact in facts if not is_tax(fact) or any(
        other is not fact and other.attribute == "fee" and other.unit in ("usd", "percent", "free")
        and same_scope(fact, other) for other in facts)]


def reviewed_duplicates(facts):
    """Keep a complete reviewed fee instead of its identical numeric extractor copy.

    This is exact same-row deduplication at ingest, not a new ranking rule.
    Disagreeing prices, dates, scopes, source identities and unrelated rows remain.
    """
    reviewed = [f for f in facts if f.attribute == "fee" and f.extractor == "curated" and f.semantics is not None]
    def duplicate(fact):
        if fact.attribute != "fee" or fact.extractor != "rules" or fact.semantics is not None:
            return False
        quote = page_text(fact.source.quote)
        return any(fact.key == other.key and fact.effective_date == other.effective_date
                   and fact.value == other.value and fact.unit == other.unit
                   and fact.source.snapshot_id == other.source.snapshot_id
                   and fact.source.url == other.source.url
                   and fact.source.content_sha256 is not None
                   and fact.source.content_sha256 == other.source.content_sha256
                   and bool(quote) and (quote in page_text(other.source.quote) or page_text(other.source.quote) in quote)
                   for other in reviewed)
    return [fact for fact in facts if not duplicate(fact)]


def presentation_statement(fact, facts):
    text = fact.value_text
    if "*" not in text or fact.attribute != "fee" or fact.semantics is None:
        return text
    if page_text(text).lstrip("* ") == _TAX:
        return text.replace("*", "")
    # Only the known asterisk marker is presentation residue, never arbitrary markup.
    if re.search(r"(?<![\d%])\*", text):
        return text
    for other in facts:
        if is_tax(other) and same_scope(fact, other):
            return text.replace("*", "")
    return text  # the unremoved marker makes the post-render completeness check fail
