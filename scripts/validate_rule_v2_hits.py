"""Manually inspect rule_detector_v2 hits to verify regex correctness.

Shows sample hits per rule with context — for visual verification before
including in training data.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_V2 = ROOT / "data/reports/bulk_rules_v2"


def main() -> None:
    by_rule = defaultdict(list)
    total = 0
    for p in sorted(RULES_V2.glob("*.json")):
        if p.name == "_summary.json":
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        for f in r["flags"]:
            by_rule[f["rule"]].append({**f, "tender_id": r["tender_id"]})
            total += 1

    print(f"Total rule_v2 hits: {total}")
    print(f"By rule: {dict(Counter(r for r in by_rule for _ in by_rule[r]))}")
    print()
    for rule, hits in by_rule.items():
        print(f"  {rule}: {len(hits)} hits")
    print("=" * 70)

    random.seed(42)
    for rule in sorted(by_rule):
        hits = by_rule[rule]
        n_show = min(10, len(hits))
        sampled = random.sample(hits, n_show) if len(hits) > n_show else hits
        print(f"\n=== {rule} ({len(hits)} hits, showing {n_show}) ===")
        for i, f in enumerate(sampled, 1):
            span = f["span_text"][:200].replace("\n", " ")
            print(f"\n  [{i}] tender={f['tender_id']} conf={f['confidence']}")
            print(f"      span: {span}")


if __name__ == "__main__":
    main()
