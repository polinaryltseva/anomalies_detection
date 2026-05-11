"""Dump all v2+2stage flags with context for manual spot-check."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from annotate_v2 import find_context, lot_text  # noqa: E402

V_DIR = ROOT / "data/reports/bulk_v2_2stage"
out_lines = []
n = 0
for p in sorted(V_DIR.glob("*.json")):
    if p.name == "_summary.json":
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    full = lot_text(r["tender_id"])
    for f in r["flags"]:
        n += 1
        ctx = find_context(full, f["span_text"])
        out_lines.append(f"## #{n} [{f['label']}] {r['tender_id']} (conf={f['confidence']})\n")
        out_lines.append(f"**section**: {f['section']}\n")
        out_lines.append(f"**rationale**: {f['rationale']}\n")
        out_lines.append(f"**span**: «{f['span_text']}»\n")
        out_lines.append(f"\n```\n{ctx[:1500]}\n```\n")
        out_lines.append("\n---\n")

out = ROOT / "data/labeled/v2_2stage_flag_review.md"
out.write_text("\n".join(out_lines), encoding="utf-8")
print(f"Wrote {n} flags to {out}")
