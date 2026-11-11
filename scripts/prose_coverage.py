"""Measure verified description/eligibility coverage from the runtime's store."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dump_eval_keys import build_system


def main():
    ks = build_system()
    registry = ks.registry
    products = {pid for pid in registry.aliases().values()
                if registry.published(pid) & {"description", "eligibility"}}
    snapshot = ks.store.snapshots()[-1][0]
    present = {pid for (pid, attr), facts in ks.store.by_product_attr[snapshot].items()
               if attr in ("description", "eligibility") and any(f.extractor == "curated" for f in facts)}
    print("coverage: {}/{} products with a verified description or eligibility fact in crawl 05".format(
        len(products & present), len(products)))
    print("uncovered: " + ", ".join(sorted(products - present)))


if __name__ == "__main__":
    main()
