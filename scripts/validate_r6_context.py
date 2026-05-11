"""Pull surrounding context for R6 (ФИО+company) hits to verify if they are
real COI signals or just standard заказчик contact info."""
from __future__ import annotations

import json
import re
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
    r6_hits = []
    for p in sorted(RULES_V2.glob("*.json")):
        if p.name == "_summary.json":
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        for f in r["flags"]:
            if f["rule"] == "R6":
                r6_hits.append({"tender_id": r["tender_id"], **f})

    # Sample 8 hits, get ±300 chars context
    print(f"Total R6 hits: {len(r6_hits)}")
    print(f"Showing 8 with full context:")
    print("=" * 70)

    seen_lots = set()
    shown = 0
    for hit in r6_hits:
        if hit["tender_id"] in seen_lots:
            continue
        seen_lots.add(hit["tender_id"])

        text = gather_text(hit["tender_id"])
        span = hit["span_text"]
        idx = text.find(span[:60])  # Find by first 60 chars (avoid mojibake)
        if idx < 0:
            continue
        before = text[max(0, idx - 300):idx]
        after = text[idx + len(span):idx + len(span) + 300]
        print(f"\n[{hit['tender_id']}] R6: {hit['rationale']}")
        print(f"  ----CONTEXT----")
        print(f"  ...{before}")
        print(f"  >>> SPAN: {span}")
        print(f"  {after}...")
        print(f"  ---------------")
        shown += 1
        if shown >= 8:
            break


if __name__ == "__main__":
    main()
