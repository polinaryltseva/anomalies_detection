"""Dump all model flags on 20 held-out lots для honest manual verification."""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from annotate_v2 import find_context, lot_text

heldout = ['169601988','169625654','169607912','169633468','169608001','169596411','169633409','169629628','169632529','169618150',
           '169614080','169632308','169625569','169618154','169548312','169638017','169633404','169602026','169568252','169629511']

pipelines = {
    "ft_v1": "data/reports/bulk_ft",
    "ft_v2": "data/reports/bulk_ft_v2",
    "rules": "data/reports/bulk_rules",
    "v3+2s": "data/reports/bulk_v3",
}

for name, d in pipelines.items():
    lines = [f"# {name} flags on 20 held-out lots", ""]
    n = 0
    for t in heldout:
        p = ROOT / f"{d}/{t}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if not r["flags"]:
            continue
        full = lot_text(t)
        lines.append(f"## {t} (risk={r['overall_risk_score']:.2f}, {len(r['flags'])} flags)")
        for fl in r["flags"]:
            n += 1
            ctx = find_context(full, fl["span_text"])
            lines.append(f"\n### #{n} [{fl['label']}] conf={fl.get('confidence', 0)}")
            lines.append(f"**span**: «{fl['span_text']}»")
            if fl.get('rationale'):
                lines.append(f"**rationale**: {fl['rationale'][:200]}")
            lines.append("**context**:")
            lines.append("```")
            lines.append(ctx[:1200] if ctx else "NO CONTEXT")
            lines.append("```")
        lines.append("")

    out = ROOT / f"data/labeled/heldout_review_{name.replace('+','').replace(' ','_')}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{name}: {n} flags -> {out.name} ({out.stat().st_size//1024}KB)")
