"""Pull full context for each flag from all 3 models on heldout lots.

Output: data/eval/heldout_flags_with_context.json — list of flags with ±400 char
context, ready for manual verification.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

RAW = ROOT / "data/raw/bulk"
LOTS = json.loads((ROOT / "data/eval/heldout_v3_lots.json").read_text(encoding="utf-8"))["lots"]

MODELS = {
    "FT_v2": ROOT / "data/reports/heldout_ftv2",
    "FT_v3a": ROOT / "data/reports/heldout_ftv3a",
    "FT_v3a_mini": ROOT / "data/reports/heldout_ftv3a_mini",
}


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


def find_context(text: str, span: str, window: int = 400) -> str:
    if not text or not span:
        return ""
    span = span.strip()
    # Try first 60 chars of span (avoid noise from very long spans)
    probe = span[:60]
    idx = text.find(probe)
    if idx < 0:
        norm_text = re.sub(r"\s+", " ", text)
        norm_probe = re.sub(r"\s+", " ", probe)
        idx = norm_text.find(norm_probe)
        if idx < 0:
            return f"NO_CONTEXT span={span[:80]!r}"
        text = norm_text
    s = max(0, idx - window)
    e = min(len(text), idx + len(span) + window)
    return text[s:idx] + "【" + text[idx:idx + len(span)] + "】" + text[idx + len(span):e]


def main() -> None:
    text_cache: dict[str, str] = {}

    flags_with_ctx = []
    for lot_id in LOTS:
        for model_name, mdir in MODELS.items():
            p = mdir / f"{lot_id}.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            for f in r.get("flags", []):
                if lot_id not in text_cache:
                    text_cache[lot_id] = lot_text(lot_id)
                ctx = find_context(text_cache[lot_id], f["span_text"])
                flags_with_ctx.append({
                    "tender_id": lot_id,
                    "model": model_name,
                    "label": f["label"],
                    "section": f.get("section", ""),
                    "span_text": f["span_text"][:400],
                    "context": ctx[:1500],
                    "confidence": f.get("confidence", None),
                    "rationale": f.get("rationale", ""),
                })

    out = ROOT / "data/eval/heldout_flags_with_context.json"
    out.write_text(json.dumps(flags_with_ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(flags_with_ctx)} flag-instances with context -> {out}")
    from collections import Counter
    print(f"By model: {dict(Counter(f['model'] for f in flags_with_ctx))}")


if __name__ == "__main__":
    main()
