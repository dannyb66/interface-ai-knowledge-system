"""Explicit fee conditions are hard scope, never implicit customer defaults."""
from __future__ import annotations

import re

CONDITION_VALUES = {
    "membership": frozenset({"member", "non_member"}),
    "deposit_disposition": frozenset({"deposited", "not_deposited"}),
    "statement_delivery": frozenset({"e_statements", "without_e_statements"}),
    "usage_allowance": frozenset({"within_eight_free", "after_eight_free"}),
    "card": frozenset({"debit", "credit"}),
}


def validate_conditions(qualifiers):
    for key, allowed in CONDITION_VALUES.items():
        if key in qualifiers and qualifiers[key] not in allowed:
            raise ValueError("unknown condition value for " + key)


def _other_membership_scope(text, start, end):
    """Explicit outside affiliation cannot establish membership in the serving credit union."""
    tail = text[end:]
    if re.match(r"\s+elsewhere\b", tail):
        return True
    affiliation = re.match(r"\s+(?:of|at|with)\s+([^?.;,]+)", tail)
    if re.match(r"\s+with\s+(?:(?:the|my|some|no)\s+)?(?:coins?|proceeds|money|cash|e[ -]?statements?|paper statements?)\b", tail):
        affiliation = None  # a separate fee condition, not a membership provider
    serving = (r"(?:dupaco(?:'s)?(?: credit union)?|the credit union)"
               r"(?=$|\s+(?:deposit(?:ing|ed)?|and|but|who|with|for|using|asking|paying|counting|when|if|currently)\b)")
    if affiliation and (not re.match(serving, affiliation.group(1))
                        or re.search(r"\bor\b", affiliation.group(1))):
        return True
    parts = re.split(r"[.!?;,\n]|\b(?:and|or|but|for|as|am)\b", text[:start])
    prefix = re.sub(r"^is\s+", "", parts[-1].strip())
    if prefix and not re.search(r"\bfees?\b", prefix) and (len(parts) > 1 or re.match(r"(?:a|an|the)\s+", prefix)):
        allowed = {"a", "an", "the", "current", "active", "existing", "new", "longtime", "long", "time",
                   "loyal", "registered", "regular", "dupaco", "s", "credit", "union", "already", "still", "currently"}
        return bool(set(re.findall(r"[a-z]+", prefix)) - allowed)
    return False


def _unresolved_condition(text, start, end, key):
    """Reject unresolved scope around a match without negating a neighboring slot.

    Known negatives are part of their matched phrase. Any remaining negation or
    uncertainty before that phrase cannot be interpreted as an affirmative value.
    Clause and condition boundaries prevent "not a member depositing coins" from
    accidentally negating the independently stated deposit disposition.
    """
    prefix = re.split(r"[.!?;,\n]|\b(?:and|or|but|members?|membership|cards?|coins?|proceeds|"
                      r"e[ -]?statements?)\b", text[:start])[-1]
    if key == "membership" and _other_membership_scope(text, start, end):
        return True
    if re.search(r"\b(?:not|never|no|without|\w+n't|unknown|unsure|uncertain|undecided|"
                 r"maybe|perhaps|possibly|might|whether|former|formerly|lapsed|expired|prospective|potential|"
                 r"future|hypothetical|pretend|considering|hoping|planning|aspiring)\b|"
                 r"\b(?:may be|would[ -]be|used to be|soon[ -]to[ -]be)\b|\b(?:non|ex)[- ]$", prefix):
        return True
    return bool(re.match(r"\s*(?:(?:status\s+)?(?:is\s+)?(?:unknown|uncertain|unclear|undetermined)\b|"
                         r"or\s+not\b|[- ]to[- ]be\b|in\s+the\s+past\b|previously\b|formerly\b)", text[end:]))


def query_conditions(text):
    """Read narrow, explicit conditions; contradictory values remain invalid slots."""
    text = text.lower().replace("’", "'")
    found = {}
    patterns = {
        "card": {"debit": r"\bdebit(?:[ -]cards?)?\b", "credit": r"\bcredit[ -]cards?\b"},
        "membership": {
            "non_member": r"\bnon[ -]?members?\b|\bnot (?:a |an? existing )?member\b|\b(?:without|don't have|do not have) (?:a )?membership\b",
            "member": r"(?<!non-)(?<!non )\bmembers?\b|\bbelong to (?:the credit union|dupaco)\b"},
        "deposit_disposition": {
            "not_deposited": r"\b(?:not|never|without|don't|do not|won't|will not) (?:be |going to )?deposit(?:ed|ing)?\b|\bcash(?:ing)? (?:the )?coins?\b",
            "deposited": r"\bdeposit(?:ed|ing)? (?:the |my |these )?(?:coins?|proceeds|money)\b|\b(?:coins?|proceeds) (?:are |will be )?deposited\b"},
        "statement_delivery": {
            "without_e_statements": r"\b(?:(?:without|no) |(?:not|never|don't|do not|won't|will not) (?:use |have |receive |(?:signed up|sign up|enrolled|enroll) for )?)e[ -]?statements?\b|\bpaper statements?\b",
            "e_statements": r"\be[ -]?statements?\b"},
        "usage_allowance": {
            "after_eight_free": r"\b(?:after (?:the )?(?:first )?(?:eight|8)|(?:ninth|9th|subsequent) (?:transaction|inquiry|withdrawal))\b",
            "within_eight_free": r"\b(?:first (?:eight|8)|within (?:the )?(?:eight|8) free)\b"},
    }
    for key, values in patterns.items():
        remaining, matched, unresolved = text, [], False
        for value, pattern in values.items():
            matches = list(re.finditer(pattern, remaining))
            if matches:
                matched.append(value)
                unresolved |= any(_unresolved_condition(text, m.start(), m.end(), key) for m in matches)
                remaining = re.sub(pattern, lambda m: " " * len(m.group()), remaining)
        if matched:
            found[key] = matched[0] if len(matched) == 1 and not unresolved else "contradictory"
    return found


def source_conditions(label, value_text):
    """Scope the existing numeric fee extractor from its own schedule wording."""
    text = (label + " " + value_text).lower()
    out = {}
    if re.search(r"\bnon[ -]?members?\b", text):
        out["membership"] = "non_member"
    elif re.search(r"\b(?:for members|members only)\b", text):
        out["membership"] = "member"
    if "free if signed up for e-statements" in text:
        out["statement_delivery"] = "without_e_statements"
    if re.search(r"\b(?:after|over) (?:the )?(?:first )?(?:eight|8)\b", text):
        out["usage_allowance"] = "after_eight_free"
    return out


def select_conditions(facts, query):
    """Each OR branch is independently sufficient; missing required scope refuses it.

    Absent fact slots are unrestricted, so a known nonmember branch need not also
    know deposit disposition. An omitted query slot never satisfies a scoped fact.
    """
    asked = dict(query.slots)
    if any(asked.get(key) == "contradictory" for key in CONDITION_VALUES):
        return []
    from .fee_semantics import retain_scoped_companions
    return retain_scoped_companions([fact for fact in facts if all(asked.get(key) == value
            for key, value in fact.qualifiers if key in CONDITION_VALUES)])
