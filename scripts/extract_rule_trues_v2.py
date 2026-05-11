"""Extract silver TRUE labels from rule_detector_v2 outputs (R1 only).

R3/R3b dropped: all hits were legal exceptions (spare parts for existing equipment).
R6 dropped: hits matched заказчик's contact persons, not vendor COI.
Only R1 (empty evaluation criteria) is reliable enough for silver labels.

Cap: ≤2 per tender to avoid R1 pattern domination.
Skip lots already in manual annotations (v1/v2/v3/ensemble/gpt55/bottom-10).

Output: data/labeled/rule_trues_v2.jsonl
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_V2 = ROOT / "data/reports/bulk_rules_v2"
OUT = ROOT / "data/labeled/rule_trues_v2.jsonl"


def main() -> None:
    # Lots already in any annotation source — skip them
    annotated_lots = set()
    for path in [
        ROOT / "data/labeled/bulk_flag_annotations.jsonl",
        ROOT / "data/labeled/v2_flag_annotations.jsonl",
        ROOT / "data/labeled/v3_flag_annotations.jsonl",
        ROOT / "data/labeled/ensemble_annotations.jsonl",
        ROOT / "data/labeled/gpt55_annotations.jsonl",
    ]:
        if path.exists():
            for l in path.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    annotated_lots.add(json.loads(l)["tender_id"])
    bottom_10 = {'169629544', '169596415', '169608004', '169633366', '169618156',
                 '169608015', '169633302', '169618157', '169625477', '169629441'}
    annotated_lots |= bottom_10
    print(f"Lots already annotated (skip): {len(annotated_lots)}")

    # Collect R1 hits per tender
    by_tid = defaultdict(list)
    for p in sorted(RULES_V2.glob("*.json")):
        if p.name == "_summary.json":
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if r["tender_id"] in annotated_lots:
            continue
        for f in r["flags"]:
            if f["rule"] != "R1":
                continue
            by_tid[r["tender_id"]].append(f)

    # Cap ≤2 per tender, prefer longer spans
    CAP = 2
    silver = []
    for tid, flags in by_tid.items():
        flags.sort(key=lambda x: -len(x["span_text"]))
        for f in flags[:CAP]:
            silver.append({
                "tender_id": tid,
                "label": "ambiguous_evaluation_criteria",
                "section": "evaluation",
                "span_text": f["span_text"][:300],
                "confidence": 0.9,
                "rationale": "R1: empty evaluation criteria — verified pattern (95%+ precision)",
                "regulatory_reference": "EU Directive 2014/24/EU Art. 67",
                "verdict": "TRUE",
                "source": "rule_v2_R1",
            })

    print(f"\nSilver labels (R1 only):")
    print(f"  Total: {len(silver)}")
    print(f"  Unique tenders: {len(by_tid)}")
    print(f"  Cap: <={CAP} per tender")

    with OUT.open("w", encoding="utf-8") as f:
        for d in silver:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()
