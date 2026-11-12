"""Deterministic source-derived route hints, built only after ingestion.

One target is an entity/attribute scope, never an individual paragraph to emit.
Aliases and verified claim vocabulary supply tokens; evaluation questions never
enter this index. Scores are lexical overlap measures, not probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

_STOP = frozenset("a an the and or to of in on at by for from with as is are was were be been do does did can could would should will what which who why how when where i my me we our your you it its this that these those about according say says said tell describe describes explain dupaco credit union please have has had may might into through".split())
_ATTRIBUTE_WORDS = {
    "description": "purpose use meaning overview benefits features works help definition",
    "eligibility": "eligible qualify qualification requirements criteria conditions join application",
    "fee": "fee cost charge price pay payment",
}


def tokens(text):
    result = set()
    for word in re.findall(r"[a-z]+", str(text).lower()):
        if word in _STOP or len(word) < 3:
            continue
        if word.endswith("ies") and len(word) > 5:
            word = word[:-3] + "y"
        elif word.endswith("ing") and len(word) > 6:
            word = word[:-3]
        elif word.endswith("ers") and len(word) > 6:
            word = word[:-3]
        elif word.endswith("er") and len(word) > 5:
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 4:
            word = word[:-1]
        if word.endswith("e") and len(word) > 5:
            word = word[:-1]
        result.add(word)
    return frozenset(result)


@dataclass(frozen=True)
class Route:
    product_id: str
    attribute: str
    score: float
    anchor_matches: int
    token_matches: int


class LexicalIndex:
    version = "source-routes-v1"

    def __init__(self, rows=(), generation="empty", latest_snapshot=None, latest_day=None):
        self.rows = tuple(rows)
        self.generation = generation
        self.latest_snapshot = latest_snapshot
        self.latest_day = latest_day
        vocabulary = set().union(*(row[3] for row in self.rows)) if self.rows else set()
        self._weights = {word: math.log((len(self.rows) + 1) / (sum(word in r[3] for r in self.rows) + 1)) + 1
                         for word in vocabulary}
        self._unseen_weight = math.log(len(self.rows) + 1) + 1

    @classmethod
    def build(cls, store, registry):
        scopes = {}
        for sid in sorted(store.by_product_attr):
            for (pid, attr), facts in sorted(store.by_product_attr[sid].items()):
                if attr not in _ATTRIBUTE_WORDS:
                    continue
                verified = [f for f in facts if f.extractor == "curated" or f.semantics is not None]
                if not verified or attr not in registry.published(pid):
                    continue
                scope = scopes.setdefault((pid, attr), {"vocabulary": set(), "provenance": set()})
                for fact in verified:
                    scope["vocabulary"].update(tokens(fact.value_text))
                    scope["provenance"].add((sid, fact.source.canonical_url, fact.source.content_sha256))
        aliases = {}
        for alias, pid in sorted(registry.aliases().items()):
            aliases.setdefault(pid, set()).update(tokens(alias))
        rows = []
        for (pid, attr), scope in sorted(scopes.items()):
            anchors = frozenset(aliases.get(pid, ()))
            vocabulary = frozenset(scope["vocabulary"]) | anchors | tokens(_ATTRIBUTE_WORDS[attr])
            rows.append((pid, attr, anchors, vocabulary, tuple(sorted(scope["provenance"], key=repr))))
        payload = [(pid, attr, sorted(anchors), sorted(words), provenance) for pid, attr, anchors, words, provenance in rows]
        generation = hashlib.sha256(json.dumps([cls.version, payload], sort_keys=True).encode()).hexdigest()
        latest = store.snapshots()[-1] if store.snapshots() else (None, None)
        return cls(rows, generation, latest[0], latest[1])

    def rank(self, text, product_id=None, attribute=None):
        wanted = tokens(text)
        rows = [row for row in self.rows if (product_id is None or row[0] == product_id)
                and (attribute is None or row[1] == attribute)
                and (self.latest_snapshot is None or any(p[0] == self.latest_snapshot for p in row[4]))]
        weights = {word: self._weights.get(word, self._unseen_weight) for word in wanted}
        denominator = sum(weights.values())
        found = []
        for pid, attr, anchors, words, _ in rows:
            overlap, anchor = wanted & words, wanted & anchors
            score = sum(weights[word] for word in overlap) / denominator if denominator else 0.0
            found.append(Route(pid, attr, score, len(anchor), len(overlap)))
        return sorted(found, key=lambda r: (-r.score, -r.anchor_matches, r.product_id, r.attribute))
