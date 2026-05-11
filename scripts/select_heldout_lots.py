"""Select 20 held-out lots for FT v3 evaluation.

Requirements:
- Lots NOT in any training annotation (v1, v2, v3, ensemble, gpt55, rule_v2)
- Lots NOT in bottom-10 (already used as negatives)
- Mix: ~10 from existing v3+2s reports (likely contain anomalies) + ~10 random
  (test specificity on natural distribution)
- Reproducible: seed=42

Output: data/eval/heldout_v3_lots.json (list of lot IDs)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bulk"
V3_REPORTS = ROOT / "data/reports/bulk_v3"

random.seed(42)


def main() -> None:
    # Lots already used in any annotation
    annotated_lots = set()
    for path in [
        ROOT / "data/labeled/bulk_flag_annotations.jsonl",
        ROOT / "data/labeled/v2_flag_annotations.jsonl",
        ROOT / "data/labeled/v3_flag_annotations.jsonl",
        ROOT / "data/labeled/ensemble_annotations.jsonl",
        ROOT / "data/labeled/gpt55_annotations.jsonl",
        ROOT / "data/labeled/rule_trues_v2.jsonl",
    ]:
        if path.exists():
            for l in path.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    annotated_lots.add(json.loads(l)["tender_id"])

    bottom_10 = {'169629544', '169596415', '169608004', '169633366', '169618156',
                 '169608015', '169633302', '169618157', '169625477', '169629441'}
    annotated_lots |= bottom_10

    print(f"Excluded lots (in training): {len(annotated_lots)}")

    # All lots with parsed text
    all_lots = sorted([d.name for d in RAW.iterdir() if d.is_dir()])
    print(f"Total lots in corpus: {len(all_lots)}")

    available = [l for l in all_lots if l not in annotated_lots]
    print(f"Available (not in training): {len(available)}")

    # Pool 1: lots from v3+2s reports (high signal)
    v3_lots = []
    for p in V3_REPORTS.glob("*.json"):
        if p.name == "_summary.json":
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r["tender_id"] in available and r.get("overall_risk_score", 0) >= 0.5:
            v3_lots.append({
                "tender_id": r["tender_id"],
                "risk": r["overall_risk_score"],
                "n_flags": len(r.get("flags", [])),
            })
    v3_lots.sort(key=lambda x: -x["risk"])
    print(f"v3+2s available with risk>=0.5: {len(v3_lots)}")

    # Pick 10 from v3+2s pool (mid-high risk to find diverse anomalies)
    v3_pool = [l for l in v3_lots if 0.6 <= l["risk"] <= 0.95]
    random.shuffle(v3_pool)
    signal_lots = v3_pool[:10]

    # Pool 2: random lots (mix — may include clean ones for specificity)
    v3_lot_ids = {l["tender_id"] for l in v3_lots}
    random_pool = [l for l in available if l not in v3_lot_ids and l not in {x["tender_id"] for x in signal_lots}]
    random.shuffle(random_pool)
    random_lots = [{"tender_id": tid, "risk": None, "n_flags": None} for tid in random_pool[:10]]

    heldout = signal_lots + random_lots
    print(f"\nSelected: {len(heldout)} lots")
    print(f"  From v3+2s mid-high risk: {len(signal_lots)}")
    print(f"  Random: {len(random_lots)}")

    print("\nLot list:")
    for l in heldout:
        risk_str = f"risk={l['risk']:.2f}" if l['risk'] else "random"
        print(f"  {l['tender_id']}  {risk_str}")

    out = {
        "lots": [l["tender_id"] for l in heldout],
        "details": heldout,
        "seed": 42,
        "strategy": "10 mid-high-risk from v3+2s + 10 random",
    }
    out_path = ROOT / "data/eval/heldout_v3_lots.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
