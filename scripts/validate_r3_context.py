"""Pull surrounding context for R3 / R3b hits to determine if they are
real ban-equivalent violations or legal exceptions for spare parts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

RAW = ROOT / "data/raw/bulk"
RULES_V2 = ROOT / "data/reports/bulk_rules_v2"


def gather_text(lot_id: str) -> str:
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


def main() -> None:
    r3_hits = []
    for p in sorted(RULES_V2.glob("*.json")):
        if p.name == "_summary.json":
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        for f in r["flags"]:
            if f["rule"] in ("R3", "R3b"):
                r3_hits.append({"tender_id": r["tender_id"], **f})

    print(f"Total R3/R3b hits: {len(r3_hits)}")
    print("=" * 70)

    for hit in r3_hits:
        text = gather_text(hit["tender_id"])
        span = hit["span_text"]
        idx = text.find(span[:30])
        if idx < 0:
            continue
        before = text[max(0, idx - 400):idx]
        after = text[idx + len(span):idx + len(span) + 400]
        print(f"\n[{hit['tender_id']}] {hit['rule']}: span={span!r}")
        print(f"  ...{before}")
        print(f"  >>> {span}")
        print(f"  {after}...")
        print()


if __name__ == "__main__":
    main()
