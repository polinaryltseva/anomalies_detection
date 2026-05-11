"""Auto-annotate v2+2stage output."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from annotate_v2 import check_whitelist, find_context, lot_text  # noqa: E402

V_DIR = ROOT / "data/reports/bulk_v2_2stage"
OUT = ROOT / "data/labeled/bulk_v2_2stage_annotations.jsonl"

reports = sorted(V_DIR.glob("*.json"))
reports = [r for r in reports if r.name != "_summary.json"]
rows = []
for p in reports:
    r = json.loads(p.read_text(encoding="utf-8"))
    full = lot_text(r["tender_id"])
    for f in r["flags"]:
        ctx = find_context(full, f["span_text"])
        wl, rule = check_whitelist(f["span_text"], ctx, f["label"])
        rows.append({
            "tender_id": r["tender_id"],
            "label": f["label"], "section": f["section"],
            "span": f["span_text"][:200], "confidence": f.get("confidence", 0),
            "auto_verdict": "FALSE_W" if wl else "MAYBE_TRUE",
            "wl_rule": rule, "lot_risk": r["overall_risk_score"],
        })

with OUT.open("w", encoding="utf-8") as fh:
    for x in rows:
        fh.write(json.dumps(x, ensure_ascii=False) + "\n")

print(f"v2+2stage reports: {len(reports)}")
print(f"Total flags: {len(rows)}")
v = Counter(r["auto_verdict"] for r in rows)
print(f"Verdicts: {dict(v)}")
maybe_true_pct = 100 * v.get("MAYBE_TRUE",0) / len(rows) if rows else 0
print(f"Heuristic precision_upper: {maybe_true_pct:.1f}%")

by_label = defaultdict(Counter)
for r in rows:
    by_label[r["label"]][r["auto_verdict"]] += 1
print("\nBy label:")
for lbl in sorted(by_label):
    c = by_label[lbl]
    n = sum(c.values())
    mt = c.get("MAYBE_TRUE",0)
    print(f"  {lbl}: {mt}/{n} = {100*mt/n:.0f}%")
