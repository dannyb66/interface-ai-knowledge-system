"""Required eligibility claims survive source verification and later selection."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re


@dataclass(frozen=True)
class ClaimGroup:
    group_id: str
    claim_id: str
    required_claim_ids: tuple


def claim_identity(entry):
    if entry.semantics is not None:
        return entry.semantics.claim_id
    quote = entry.quote if hasattr(entry, "quote") else entry.source.quote
    stable = [entry.product_id, entry.attribute, list(entry.qualifiers), quote]
    return "legacy:" + hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]


def group_from_dict(raw):
    if not isinstance(raw, dict) or set(raw) != set(ClaimGroup.__dataclass_fields__):
        raise ValueError("invalid claim group fields")
    required = raw["required_claim_ids"]
    values = [raw["group_id"], raw["claim_id"]]
    if (not isinstance(required, (tuple, list)) or not required or len(required) != len(set(required))
            or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", v)
                   for v in values + list(required))):
        raise ValueError("invalid claim group identity or required set")
    return ClaimGroup(values[0], values[1], tuple(sorted(required)))


def attach_groups(entries, declared):
    """Derive v2 groups before verification; reviewed declarations may include missing claims.

    Declarations augment the derived set. They cannot erase a known member. Legacy
    entries retain their byte-stable identity and need no schema rewrite.
    """
    groups = {}
    for entry in entries:
        annotation = entry.semantics
        grouped = entry.attribute == "eligibility" or entry.attribute == "description" and annotation and annotation.role == "procedure"
        if grouped and annotation and annotation.condition_group:
            for sid in entry.crawls:
                key = (entry.product_id, entry.attribute, annotation.condition_group, sid)
                groups.setdefault(key, set()).add(claim_identity(entry))
    if not isinstance(declared, list):
        raise ValueError("claim_groups must be a list")
    seen = set()
    for row in declared:
        if not isinstance(row, dict) or set(row) != {"entity", "attribute", "claim_set", "crawls", "required_claim_ids"}:
            raise ValueError("invalid claim_groups declaration")
        if row["attribute"] not in ("eligibility", "description") or not isinstance(row["crawls"], list) or not row["crawls"]:
            raise ValueError("claim_groups apply to crawl-scoped eligibility or reviewed procedures")
        checked = group_from_dict({"group_id": row["claim_set"], "claim_id": row["entity"],
                                   "required_claim_ids": row["required_claim_ids"]})
        for sid in row["crawls"]:
            if not isinstance(sid, str) or not sid:
                raise ValueError("invalid claim group crawl")
            key = (row["entity"], row["attribute"], row["claim_set"], sid)
            if not any((e.product_id, e.attribute) == key[:2] and sid in e.crawls for e in entries):
                raise ValueError("claim group does not match any declared entity/attribute/crawl")
            existing = [e for e in entries if (e.product_id, e.attribute) == key[:2] and sid in e.crawls
                        and claim_identity(e) in checked.required_claim_ids]
            if row["attribute"] == "description" and any(e.semantics is None
                    or e.semantics.role not in ("procedure", "description")
                    or e.semantics.condition_group != row["claim_set"] for e in existing):
                raise ValueError("description groups require reviewed procedure/description claims with matching condition_group")
            if key in seen:
                raise ValueError("duplicate claim group declaration")
            seen.add(key)
            groups.setdefault(key, set()).update(checked.required_claim_ids)
            if row["attribute"] == "description":
                # An explicit reviewed bundle cannot erase a known caveat carrying
                # its group. Unrelated definitions/benefits do not join this set.
                groups[key].update(claim_identity(e) for e in entries
                    if (e.product_id, e.attribute) == key[:2] and sid in e.crawls
                    and e.semantics is not None and e.semantics.role in ("procedure", "description")
                    and e.semantics.condition_group == row["claim_set"])
    result = []
    for entry in entries:
        memberships = []
        for (pid, attr, group, sid), required in sorted(groups.items()):
            if (pid, attr) == (entry.product_id, entry.attribute) and sid in entry.crawls:
                memberships.append((sid, ClaimGroup(group, claim_identity(entry), tuple(sorted(required)))))
        result.append(replace(entry, claim_groups=tuple(memberships)))
    return result


def bind_groups(facts, entries, snapshot_id):
    """Unannotated extractor duplicates cannot bypass catalog completeness guards."""
    requirements = {}
    for entry in entries:
        for sid, group in entry.claim_groups:
            if sid == snapshot_id:
                key = (entry.product_id, entry.attribute, group.group_id)
                requirements.setdefault(key, set()).update(group.required_claim_ids)
    output = []
    for fact in facts:
        groups = tuple(ClaimGroup(group, claim_identity(fact), tuple(sorted(required)))
                       for (pid, attr, group), required in sorted(requirements.items())
                       if (pid, attr) == (fact.product_id, fact.attribute))
        output.append(replace(fact, claim_groups=groups) if groups else fact)
    return output


def complete_groups(facts):
    """An answer cannot present a surviving subset as the complete requirements."""
    required, present = {}, {}
    for fact in facts:
        for group in fact.claim_groups:
            key = (fact.product_id, fact.attribute, fact.source.snapshot_id, group.group_id)
            required.setdefault(key, set()).update(group.required_claim_ids)
            present.setdefault(key, set()).add(group.claim_id)
    return all(ids <= present[key] for key, ids in required.items())
