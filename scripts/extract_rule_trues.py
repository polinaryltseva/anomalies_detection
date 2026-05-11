"""Extract TRUE training examples from rule_detector R1 and R3 outputs.

R1 («Не предусмотрено» evaluation criteria): manually verified 5/5 → trust as TRUE
R3 (ban на «или эквивалент»): manually verified 4/4 → trust as TRUE

Skip lots already in training data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

RULES_DIR = ROOT / "data/reports/bulk_rules"
RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/labeled/rule_trues.jsonl"


def lot_text(lot_id: str) -> str:
    d = RAW / lot_id
    if not d.exists():
        return ""
    parts = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}:
            continue
        ed = extract(f)
        if ed.text:
            parts.append(ed.text)
    return "\n\n".join(parts)


# Lots already in training data
existing_v1 = [json.loads(l) for l in
               (ROOT / "data/labeled/bulk_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
existing_v2 = [json.loads(l) for l in
               (ROOT / "data/labeled/v2_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
existing_ens = [json.loads(l) for l in
                (ROOT / "data/labeled/ensemble_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
existing_gpt55 = [json.loads(l) for l in
                  (ROOT / "data/labeled/gpt55_annotations.jsonl").read_text(encoding="utf-8").splitlines()]

annotated_lots = set()
for ann in [existing_v1, existing_v2, existing_ens, existing_gpt55]:
    annotated_lots |= {a["tender_id"] for a in ann}
bottom_10 = {'169629544', '169596415', '169608004', '169633366', '169618156',
             '169608015', '169633302', '169618157', '169625477', '169629441'}
annotated_lots |= bottom_10

print(f"Already annotated lots: {len(annotated_lots)}")

# Get R1 + R3 flags from new lots
new_trues = []
for p in sorted(RULES_DIR.glob("*.json")):
    if p.name == "_summary.json":
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    if r["tender_id"] in annotated_lots:
        continue
    for f in r["flags"]:
        if f["label"] == "ambiguous_evaluation_criteria":  # R1
            new_trues.append({
                "tender_id": r["tender_id"],
                "label": f["label"],
                "section": "evaluation",
                "span_text": f["span_text"][:300],
                "confidence": 0.9,
                "rationale": "Empty evaluation criteria detected by R1 — verified pattern",
                "regulatory_reference": "EU Directive 2014/24/EU Art. 67",
                "verdict": "TRUE",
                "source": "rule_R1",
            })
        elif f["label"] == "brand_or_model_targeting" and "эквивалент" in f["span_text"].lower():
            new_trues.append({
                "tender_id": r["tender_id"],
                "label": f["label"],
                "section": "tz",
                "span_text": f["span_text"][:300],
                "confidence": 0.9,
                "rationale": "Explicit ban on 'или эквивалент' detected by R3 — verified pattern",
                "regulatory_reference": "EU Directive 2014/24/EU Art. 42(4); 223-FZ ст.3 ч.6.1",
                "verdict": "TRUE",
                "source": "rule_R3",
            })

with OUT.open("w", encoding="utf-8") as f:
    for r in new_trues:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

from collections import Counter
print(f"\nNew rule-based TRUEs: {len(new_trues)}")
print(f"By source: {Counter(r['source'] for r in new_trues)}")
print(f"By label: {Counter(r['label'] for r in new_trues)}")
print(f"Unique lots: {len(set(r['tender_id'] for r in new_trues))}")
print(f"\nWritten -> {OUT}")
