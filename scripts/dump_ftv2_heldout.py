"""Dump FT v2 held-out flags to markdown for manual verification."""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from annotate_v2 import find_context, lot_text

heldout = ['169601988','169625654','169607912','169633468','169608001','169596411','169633409','169629628','169632529','169618150',
           '169614080','169632308','169625569','169618154','169548312','169638017','169633404','169602026','169568252','169629511']

lines = ["# FT v2 — held-out flags для manual verification", ""]
for t in heldout:
    p = ROOT / f"data/reports/bulk_ft_v2/{t}.json"
    if not p.exists():
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    if not r["flags"]:
        continue
    full = lot_text(t)
    lines.append(f"## {t} (risk={r['overall_risk_score']:.2f})")
    lines.append("")
    for fl in r["flags"]:
        ctx = find_context(full, fl["span_text"])
        lines.append(f"### [{fl['label']}] conf={fl['confidence']}")
        lines.append(f"**span**: «{fl['span_text']}»")
        lines.append(f"**rationale**: {fl['rationale']}")
        lines.append("**context**:")
        lines.append("```")
        lines.append(ctx[:1500] if ctx else "NO CONTEXT — span not found in full text")
        lines.append("```")
        lines.append("")

out = ROOT / "data/labeled/ftv2_heldout_flags.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out}")
