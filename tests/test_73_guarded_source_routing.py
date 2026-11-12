"""Source-derived routes preserve original constraints and never bypass the resolver."""
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import make_fact
from kb.config import Config
from kb.compose import product_names
from kb.diagnostics import ResolutionTrace
from kb.lexical_index import LexicalIndex, Route
from kb.question import Query, parse
from kb.registry import Registry
from kb.routing import apply_route, recover
from kb.store import FactStore
from kb.system import KnowledgeSystem


def registry():
    products = [{"product_id": "storm_claim", "family": "information", "segment": "personal",
                 "names": ["Storm insurance claim"], "aliases": ["Property insurance claim"],
                 "attributes_published": ["description"]},
                {"product_id": "fraud_report", "family": "information", "segment": "personal",
                 "names": ["Fraud report"], "aliases": [], "attributes_published": ["description"]}]
    return Registry("synthetic", products, [], [])


def index():
    facts = [make_fact("storm_claim", "description", "A storm insurance claim needs damage evidence.",
                       unit="text", extractor="curated"),
             make_fact("fraud_report", "description", "A fraud report needs evidence of fraud.",
                       unit="text", extractor="curated")]
    store = FactStore(); store.add(facts[0].source.snapshot_id, "2026-09-28", facts); store.finalize()
    return LexicalIndex.build(store, registry())


def query(text="What does an insurance storm claim require?"):
    return Query("value", None, None, (("segment", "personal"),), None, False, text, frozenset(), "original")


def config(**overrides):
    return Config(Path("unused"), lexical_routing=True, unknown_topic_routing=True, **overrides)


def test_route_scope_is_unique_and_requires_explicit_opt_in():
    original, catalog, reg = query(), index(), registry()
    assert recover(original, catalog, reg, Config(Path("unused"))) == original
    assert recover(original, catalog, reg, replace(config(), unknown_topic_routing=False)) == original
    trace = ResolutionTrace()
    routed = recover(original, catalog, reg, config(), trace)
    assert (routed.product_id, routed.attribute) == ("storm_claim", "description")
    assert routed.raw_span == original.raw_span and routed.question_numbers == original.question_numbers
    assert routed.slots == original.slots and routed.product_ids == ("storm_claim",)
    assert not routed.generic_rate and not routed.families and not routed.mentions
    assert trace.steps[-1]["generation"] == catalog.generation


def test_direct_routes_and_unsupported_requests_are_preserved():
    reg, catalog = registry(), index()
    variants = [{"as_of_error": True}, {"as_of": "2026-05-12"}, {"past": True},
                {"as_of_end": "2026-09-28"}, {"change_point": True},
                {"mentions": ((("term_months", 12),),)}, {"families": ("savings",)},
                {"product_ids": ("storm_claim", "fraud_report")},
                {"explicit_attribute": True, "attribute": "apr"}, {"slots": (("program", "construction"),)},
                {"slots": (("jumbo", True),)}, {"slots": (("segment", "business"),)},
                {"intent": "yes_no"}, {"route_blocked": True},
                {"product_id": "storm_claim", "attribute": "description"}]
    for fields in variants:
        original = replace(query(), **fields)
        assert recover(original, catalog, reg, config()) == original
    for text in ("What is my exact insurance storm claim?", "What is never covered by storm insurance?",
                 "What is an imaginary product?", "What does insurance cost?",
                 "Explain Zorblatt insurance storm claim", "Explain zorblatt insurance storm claim"):
        original = query(text)
        assert recover(original, catalog, reg, config()) == original


def test_margin_is_between_distinct_targets_and_index_order_is_stable():
    catalog = index()
    assert catalog.generation == index().generation and len(catalog.rows) == 2
    first = catalog.rows[0]
    tied = LexicalIndex([first, ("other_claim", first[1], first[2], first[3], first[4])])
    reg = registry(); reg._family["other_claim"] = "information"
    original = query("Fraud report evidence")
    assert recover(original, tied, reg, config()) == original


def test_apply_route_never_silently_drops_historical_or_explicit_attribute_state():
    target = Route("storm_claim", "description", 1, 3, 3)
    for fields in ({"generic_rate": True, "attribute": "rate"}, {"as_of": "2026-05-12"},
                   {"product_id": "fraud_report"}, {"explicit_attribute": True}):
        with pytest.raises(ValueError):
            apply_route(replace(query(), **fields), target)


def test_broad_purpose_grammar_does_not_ask_a_postal_address():
    reg = Registry.load()
    for text in ("What goals can mortgage refinancing address?", "What is Share Savings designed to offer?",
                 "What purpose does an HSA have?"):
        parsed = parse(text, None, reg)
        assert parsed.attribute == "description", (text, parsed)
    assert parse("What is the address of the Galena branch?", None, reg).attribute == "address"


def test_opt_in_routing_uses_original_query_cache_and_no_answer_time_build(monkeypatch):
    ks = KnowledgeSystem(Config.from_env(lexical_routing=True, unknown_topic_routing=True))
    ks.registry = registry()
    fact = make_fact("storm_claim", "description", "A storm insurance claim needs damage evidence.",
                     unit="text", extractor="curated")
    ks.store.add(fact.source.snapshot_id, "2026-09-28", [fact]); ks.store.finalize()
    ks._routing_index = LexicalIndex.build(ks.store, ks.registry)
    ks._warm_up()
    product_names()  # the synthetic registry intentionally lacks the production warm-up product
    monkeypatch.setattr(LexicalIndex, "build", lambda *args: pytest.fail("query-time route index build"))
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: pytest.fail("query-time file read"))
    first, second = "What does an insurance storm claim need?", "What does an insurance storm claim involve?"
    for text in (first, second):
        original = ks._parse(text, None)
        assert original.product_id is None
        answer = ks.answer(text)
        assert answer.confident and "damage evidence" in answer.text
        assert original in ks._answers
        assert ks.explain(text)["answer"] == answer.text
    assert len(ks._answers) == 2
    returned = ks.answer(first); returned.sources.clear()
    assert ks.answer(first).sources
