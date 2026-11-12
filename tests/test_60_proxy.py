# tests/test_60_proxy.py
import ast, bisect, dataclasses, hashlib, importlib.util, json, os, re, subprocess, sys
from pathlib import Path

import pytest
from conftest import make_fact

def _norm(q): return re.sub(r"[^a-z0-9 ]", "", q.lower()).split()
def _jaccard(a, b): a, b = set(_norm(a)), set(_norm(b)); return len(a & b) / max(1, len(a | b))

@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    """The proxy split built twice, under two hash seeds: no set or dict order may reach the output."""
    texts = []
    for seed in ("0", "98765"):
        out = tmp_path_factory.mktemp("proxy") / "proxy.jsonl"
        subprocess.run([sys.executable, "scripts/build_proxy_set.py", "--split", "proxy", "--out", str(out)], check=True, capture_output=True,
                       env={**os.environ, "PYTHONHASHSEED": seed})
        texts.append(out.read_text(encoding="utf-8"))
    return texts

@pytest.fixture(scope="module")
def fresh(builds): return [json.loads(l) for l in builds[0].splitlines()]  # this checkout's build, committed or not

def test_proxy_set_is_deterministic_and_well_formed(builds):
    a, b = builds; assert a == b
    items = [json.loads(l) for l in a.splitlines()]
    frozen = [json.loads(l) for l in Path("eval/proxy/proxy.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in items] == [r["id"] for r in frozen]
    # The frozen scored proxy stays unchanged. Only two source-reviewed claim scopes differ
    # when rebuilt: complete membership requirements and explicitly conditional bill-pay fees.
    deltas = []
    for fresh, old in zip(items, frozen):
        changed = {key for key in fresh.keys() | old.keys() if fresh.get(key) != old.get(key)}
        if not changed:
            continue
        deltas.append(fresh["family"])
        text = " ".join(fresh["must_include"])
        if fresh["route"] == ["value", "membership", "eligibility"]:
            assert changed == {"must_include", "must_not_include"}
            assert all(part in text for part in ("Any", "live or work", "immediate family", "Rural Ideas Network",
                       "open a savings account with $25", "keep at least $25", "Iowa, Illinois and Wisconsin"))
            assert all(part in " ".join(fresh["must_not_include"]) for part in ("or have", "$25"))
        else:
            assert fresh["route"] == ["value", "per_bill_paid_or_attempted_to_pay_free_if_signed_up_for_e_statements_fee", "fee"]
            assert changed == {"must_include"}
            assert all(part in text for part in ("Free if signed up for e-statements", "$0.50", "Sales tax may apply"))
    assert sorted(deltas) == ["eligibility"] * 3 + ["fee"] * 3
    assert len(items) >= 400 and len({i["id"] for i in items}) == len(items)
    assert {"temporal_as_of", "change_between_snapshots", "should_refuse", "branch_info", "current_value", "tier_disambiguation"} <= {i["category"] for i in items}
    assert all(i["must_include"] for i in items if i["category"] != "should_refuse")
    groups = {}
    for i in items:
        groups.setdefault(i.get("group"), []).append(i)
    assert sum(1 for g, m in groups.items() if g and len(m) >= 2) >= 30

def test_proxy_has_no_near_duplicates_of_public_or_dev():
    proxy = [json.loads(l)["question"] for l in open("eval/proxy/proxy.jsonl", encoding="utf-8")]
    known = [json.loads(l)["question"] for f in ("eval/public_eval.jsonl", "eval/dev_extra.jsonl") for l in open(f, encoding="utf-8") if l.strip()]
    assert not [(p, k) for p in proxy for k in known if _norm(p) == _norm(k) or _jaccard(p, k) > 0.8]

def _items(path="eval/proxy/proxy.jsonl"): return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
def _proxy_key(key): return hashlib.sha1(key.encode("utf-8")).hexdigest()[-1] < "d"  # the split rule: last hex digit below d
SEEDS = ("paraphrase", "probe")

def test_seeds_keep_their_originals_and_the_pre_crawl_probe():
    items = _items()
    public = {i["id"]: i for i in (json.loads(l) for l in open("eval/public_eval.jsonl", encoding="utf-8") if l.strip())}
    paras = [i for i in items if i["family"] == "paraphrase"]
    fields = ("must_include", "must_not_include", "category", "weight", "expected_sources", "group")
    assert len(paras) >= 90 and all(tuple(i[k] for k in fields) == tuple(public[i["origin"]][k] for k in fields) for i in paras)
    probes = [i for i in items if i["family"] == "probe"]
    pre = [i for i in probes if i["origin"].startswith("p05 A pre")]  # by origin: this file quotes no seed or proxy wording
    assert len(probes) >= 55 and [(i["as_of"], i["must_include"], i["must_not_include"]) for i in pre] == [(None, ["3.90%"], ["4.00%"])]  # user decision 1

def test_template_items_follow_the_key_split_and_name_their_route():
    made = [i for i in _items() if i["family"] not in SEEDS]
    assert made and all((_proxy_key(i["key"]) or i.get("split_policy") in ("publication_claim", "eligibility_scope"))
                        and i["id"].startswith("p-") and len(i["route"]) == 3
                        and bool(i["group"]) == bool(i["weight"]) for i in made)

HOLDOUT_STUB = {  # a stand-in for Task 21's templates: one family, wording of its own
    "names": {"cert_special": "{term} {jumbo} special share certificate", "cert_regular": "{term} standard share certificate",
              "ira_cert": "{term} {program} IRA {jumbo} {special} share certificate", "auto_loan": "{term} vehicle loan on a {model_year} model",
              "mortgage_purchase": "{years} fixed home purchase loan{loan_amount}", "mortgage_refi": "{years} fixed home refinance{loan_amount}"},
    "attributes": {"apy": "{intro} APY", "apr": "{intro} APR", "rate": "{intro} interest rate"},
    "families": {"rate_current": {"kind": "current", "category": "current_value", "intent": "value", "forbid": ["balance_min", "balance_max"],
                                  "templates": [{"id": "h-stub-1", "text": "Stub check: which {attr} is posted today for the {name}?"}]}}}

def test_holdout_split_needs_its_own_templates_and_takes_the_other_keys(tmp_path):
    cmd = [sys.executable, "scripts/build_proxy_set.py", "--split", "holdout"]
    r = subprocess.run(cmd + ["--out", str(tmp_path / "none.jsonl")], capture_output=True, text=True)
    assert r.returncode == 2 and "--templates" in r.stderr and not (tmp_path / "none.jsonl").exists()  # never the proxy's templates
    (tmp_path / "t.json").write_text(json.dumps(HOLDOUT_STUB))
    subprocess.run(cmd + ["--templates", str(tmp_path / "t.json"), "--out", str(tmp_path / "h.jsonl")], check=True, capture_output=True)
    hold = _items(tmp_path / "h.jsonl")
    assert hold and all(i["id"].startswith("h-stub-1-") and not _proxy_key(i["key"]) and i["family"] == "rate_current" for i in hold)
    proxy = [i["question"] for i in _items()]
    assert not [(h["question"], p) for h in hold for p in proxy if _norm(h["question"]) == _norm(p) or _jaccard(h["question"], p) > 0.8]

def test_proxy_routing_prints_the_prose_rate_then_each_family(tmp_path):
    # rows picked from the committed set by metadata: Task 21's author appends to this file blind to the proxy's wording
    items = _items()
    hours = next(i for i in items if i["family"] == "hours_branch")
    rate = next(i for i in items if i["template"] == "p-rc-1" and i["route"][1] == "cert_special")
    wrong = dict(rate, id="x-wrong", family="hours_day", route=["hours", "branch", "lobby_hours"])  # misrouted on purpose
    seed = next(i for i in items if i["family"] == "paraphrase")  # a seed: no intended route, not counted
    (tmp_path / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (hours, wrong, rate, seed)))
    out = subprocess.run([sys.executable, "scripts/proxy_routing.py", "--set", str(tmp_path / "s.jsonl")], check=True, capture_output=True, text=True).stdout.splitlines()
    assert out[0] == "prose routing rate: 0.5000 (1/2)"
    assert {"  hours_branch: 1.0000 (1/1)", "  hours_day: 0.0000 (0/1)", "  closure: n/a (0/0)", "  rate_current: 1.0000 (1/1)"} <= set(out)
    assert not [line for line in out if "paraphrase" in line]

def _kit():
    spec = importlib.util.spec_from_file_location("proxy_kit_t60", Path("scripts") / "proxy_kit.py")
    kit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit)
    return kit

def test_contested_days_are_skipped_and_the_crawls_own_day_stays():  # review C1, on a synthetic two-crawl store
    from kb.store import FactStore
    kit = _kit()
    old = make_fact("cert_regular", "apy", "2.90%", snapshot_id="01_2026-05-01_a", value=2.9, term_months=12)
    new = dataclasses.replace(make_fact("cert_regular", "apy", "3.40%", snapshot_id="02_2026-06-01_b", value=3.4, term_months=12),
                              effective_date="2026-05-20")  # crawl 2's notice dates its new value inside crawl 1's window
    for later, contested in ((new, [False, False, True, True]), (dataclasses.replace(new, effective_date="2026-04-15"), [False] * 4),
                             (dataclasses.replace(new, value=2.9, value_text="2.90%"), [False] * 4)):  # backdated; the same value
        store = FactStore()
        store.add("01_2026-05-01_a", "2026-05-01", [old]); store.add("02_2026-06-01_b", "2026-06-01", [later]); store.finalize()
        ctx = kit.Ctx(store, "proxy", {})
        assert ctx.ends == ["2026-05-31", "2026-06-01"]
        assert [ctx.contested(0, old.key, old, d) for d in ("2026-05-01", "2026-05-19", "2026-05-20", "2026-05-31")] == contested
        days = ctx.candidate_days(0, old.key, old)
        assert "2026-05-01" in days and ("2026-05-31" in days) is not contested[-1]  # the crawl's own day always stays
        assert ctx.asked_day(0, old.key, old)[0] in days

# Review C2: a refusal pair is wrong once the site states the value. A value is published when a paragraph naming the product,
# or the section under a heading naming it, holds the attribute's value pattern. The product's words are its registry names
# and aliases (a personal product's not right after "business "); a rate is a percentage with 2-3 decimals or one beside APR/APY.
VALUES = {"credit_limit": r"credit limit[^\n]{0,60}?\$\s?\d", "credit_score": r"credit score[^\n]{0,60}?\b[3-8]\d\d\b",
          "rate": r"\b\d{1,2}\.\d{2,3}\s?%|\b\d{1,2}(?:\.\d{1,3})?\s?%\s*(?:apr|apy)\b"}
PUBLISHED = (("business_platinum_visa", "credit_limit"), ("business_rewards_visa", "credit_limit"), ("mortgage_purchase", "credit_score"))

def _published(pages, product, attr):
    words = sorted({n.lower() for n in product["names"] + product["aliases"]}, key=len, reverse=True)
    def names(text):
        return any(not (product["segment"] == "personal" and text[max(0, m.start() - 9):m.start()] == "business ")
                   for w in words for m in re.finditer(r"(?<![a-z$])" + re.escape(w) + r"(?![a-z])", text))
    value = re.compile(VALUES[attr])
    for text in pages:
        sections = re.split(r"\n(?=\s*#{1,6}\s)", text)
        if any(names(p) and value.search(p) for p in re.split(r"\n\s*\n", text)) or \
                any(names(s.split("\n", 1)[0]) and value.search(s) for s in sections if re.match(r"\s*#", s)):
            return True
    return False

def test_refusal_pairs_have_no_value_on_the_newest_crawl():
    pages = [p.read_text(encoding="utf-8").lower() for p in sorted(Path("snapshots/05_2026-09-28_latest/pages").glob("*.md"))]
    products = {p["product_id"]: p for p in json.loads(Path("submission/data/products.json").read_text(encoding="utf-8"))["products"]}
    refuse = [tuple(p[:2]) for p in json.loads(Path("eval/proxy/universe.json").read_text(encoding="utf-8"))["refuse_unpublished"]]
    assert pages and not [pair for pair in refuse if _published(pages, products[pair[0]], pair[1])]
    assert [pair for pair in PUBLISHED if _published(pages, products[pair[0]], pair[1])] == list(PUBLISHED)  # the probe sees them

def test_tier_items_trap_their_sibling_tiers(fresh, store_full):  # review I1: an answer listing every tier must lose
    kit = _kit(); ctx = kit.Ctx(store_full, "proxy", {})
    tiers, missing = ("balance_min", "balance_max", "loan_amount_max"), []
    items = [i for i in fresh if i["family"] == "tier_amount"]
    for item in items:
        key = ast.literal_eval(item["key"])
        facts, row = ctx.pool(ctx.latest, key[0], key[1], None), tuple(p for p in key[2] if p[0] not in tiers)
        traps = {frozenset(kit.grader_numbers(t)) for t in item["must_not_include"]}
        missing += [(item["id"], kit.value_token(g)) for k2, g in facts.items() if k2 != key and tuple(p for p in k2[2] if p[0] not in tiers) == row
                    and not kit.same_value(g, facts[key]) and frozenset(kit.grader_numbers(kit.value_token(g))) not in traps]
    assert items and not missing

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
DATE_RE = re.compile(r"(%s) (\d{1,2}), (\d{4})" % "|".join(MONTHS))

def test_no_gating_item_asks_a_contested_day(fresh, store_full):  # review C1: the contested days only in a non-gating family
    kit = _kit(); ctx = kit.Ctx(store_full, "proxy", {})
    def contested(item):
        key, out = ast.literal_eval(item["key"]), []
        days = [item["as_of"]] if item["as_of"] else ["%s-%02d-%s" % (m.group(3), MONTHS.index(m.group(1)) + 1, m.group(2).zfill(2)) for m in DATE_RE.finditer(item["question"])]
        for day in days:
            i = bisect.bisect_right(ctx.days, day) - 1
            f = ctx.pool(i, key[0], key[1], day).get(key)
            out.append(f is not None and ctx.contested(i, key, f, day))
        return out
    asked = [i for i in fresh if i["family"] in ("rate_as_of", "rate_change")]
    assert asked and not [i["id"] for i in asked if any(contested(i))]
    shown = [i for i in fresh if i["family"] == "contested_day"]
    assert 5 <= len(shown) <= 25 and all(i["weight"] == 0 and i["group"] is None and contested(i) == [True] for i in shown)


def test_generated_family_coverage_cannot_be_replaced_by_seeds(fresh):
    from collections import Counter
    counts = Counter(item['family'] for item in fresh)
    minimum = {'rate_current': 200, 'rate_as_of': 100, 'rate_change': 300,
               'tier_amount': 130, 'refuse_unpublished': 21, 'hours_branch': 30,
               'hours_day': 60, 'hours_unlisted': 12, 'closure': 4,
               'count': 3, 'count_year': 5, 'contested_day': 5}
    assert not {family: counts[family] for family, floor in minimum.items() if counts[family] < floor}


def test_dated_selection_uses_runtime_selector_with_identical_order(store_full):
    from kb.temporal import select_dated
    kit = _kit()
    assert kit.select_dated is select_dated
    ctx = kit.Ctx(store_full, 'proxy', {})
    for pair in (('branch', 'lobby_hours'), ('branch', 'closure_date'), ('branch_count', 'count')):
        facts = [f for f in store_full.by_product_attr[ctx.ids[-1]].get(pair, []) if f.published_date]
        assert ctx.dated(*pair) == select_dated(facts, None)
        if facts:
            day = min(f.published_date for f in facts)
            assert kit.select_dated(facts, day) == select_dated(facts, day)


def test_realistic_tier_amounts_and_unchanged_spans(fresh):
    kit = _kit()
    amounts = [float(re.search(r'\$([\d,.]+)', item['question']).group(1).replace(',', ''))
               for item in fresh if item['family'] == 'tier_amount']
    assert amounts and min(amounts) >= 100
    assert kit.tier_amount({'balance_min': 0, 'balance_max': 99.99}, 0) is None
    assert kit.tier_amount({'balance_min': 0, 'balance_max': 100}, 0) == 100
    assert kit.tier_amount({'loan_amount_max': 100}, 0) == 100
    unchanged = [item for item in fresh if item['family'] == 'rate_change'
                 and len(item['must_include']) == 2 and item['must_include'][0] == item['must_include'][1]]
    assert len(unchanged) >= 20


def test_hours_trap_other_branches_without_trapping_correct_schedule(fresh, store_full):
    kit = _kit()
    ctx = kit.Ctx(store_full, 'proxy', {})
    tested = 0
    for item in fresh:
        if item['family'] not in ('hours_branch', 'hours_day'):
            continue
        key = ast.literal_eval(item['key'])
        branch = dict(key[2])['branch_name']
        correct = ' | '.join(item['must_include'])
        candidates = [kit.value_token(f) for f in ctx.dated(key[0], key[1])
                      if dict(f.qualifiers).get('branch_name') != branch]
        expected = [token for token in candidates if token and not kit.contains(correct, token)]
        assert all(not kit.contains(correct, trap) for trap in item['must_not_include'])
        assert all(any(kit.contains(trap, token) for trap in item['must_not_include']) for token in expected)
        tested += bool(expected)
    assert tested >= 10
    refused = [item for item in fresh if item['family'] == 'hours_unlisted']
    assert refused and all(item['category'] == 'should_refuse' and not item['must_include'] for item in refused)


def test_routing_misses_rejects_holdout_before_parsing(tmp_path):
    path = tmp_path / 'synthetic.jsonl'
    secret = 'synthetic private marker'
    path.write_text(json.dumps({'id': 'h-synthetic', 'question': secret}) + '\n', encoding='utf-8')
    run = subprocess.run([sys.executable, 'scripts/proxy_routing.py', '--set', str(path), '--misses'],
                         capture_output=True, text=True)
    assert run.returncode == 2 and secret not in run.stdout + run.stderr and not run.stdout


def test_minority_prose_family_can_trigger_routing_gate(tmp_path):
    rate = next(item for item in _items() if item['template'] == 'p-rc-1' and item['route'][1] == 'cert_special')
    rows = [dict(rate, id='synthetic-%d' % index, family='closure', route=['status', 'branch', 'closure_date'])
            for index in range(4)]
    path = tmp_path / 'routing.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    run = subprocess.run([sys.executable, 'scripts/proxy_routing.py', '--set', str(path), '--gate'],
                         capture_output=True, text=True)
    assert run.returncode == 1
    assert 'minimum prose family routing: 0.0000; routing-index trigger: yes' in run.stdout


def test_family_report_excludes_seeds_and_zero_weight_diagnostics():
    spec = importlib.util.spec_from_file_location('proxy_report_t60', Path('scripts/proxy_report.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    items = [{'id': 'one', 'family': 'rate_current'}, {'id': 'two', 'family': 'probe'},
             {'id': 'zero', 'family': 'contested_day'}]
    results = [{'id': 'one', 'score': 1, 'weight': 1, 'trap_hits': []},
               {'id': 'two', 'score': 0, 'weight': 10, 'trap_hits': []},
               {'id': 'zero', 'score': 0, 'weight': 0, 'trap_hits': []}]
    summary = module.summarize(items, results)
    assert summary['generated_score'] == summary['generated_macro'] == 1
    assert summary['seed_score'] == 0 and summary['macro_seed_blend'] == 0.5
    assert summary['families']['contested_day']['score'] is None
    assert 'seed_score' in module.gate_failures(summary, {'errors': 0, 'consistency': {'paraphrase_consistency': 1}})
    with pytest.raises(ValueError):
        module.summarize(items, results[:1])
