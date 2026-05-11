"""Готовит data/labeled/flags_review_pack.json — все ~123 флага с контекстом
для ручной разметки (Claude или человек): кусок текста до/после span, +
вся метаинформация (lot, label, rationale, regulatory_ref).

Также пишет markdown-версию для удобства чтения.
"""

from __future__ import annotations

import json
import re
import sys
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

REPORTS_DIRS = [ROOT / "data/reports/real_lots", ROOT / "data/reports/lots_v2"]
RAW_DIRS = [ROOT / "data/raw/manual", ROOT / "data/raw/lots"]
OUT_DIR = ROOT / "data/labeled"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONTEXT_BEFORE = 800
CONTEXT_AFTER = 800


def _flag_id(tender_id: str, label: str, span: str) -> str:
    return md5(f"{tender_id}|{label}|{span[:200]}".encode()).hexdigest()[:16]


_text_cache: dict[str, str] = {}


def _lot_text(lot_id: str) -> str:
    if lot_id in _text_cache:
        return _text_cache[lot_id]
    for raw_root in RAW_DIRS:
        d = raw_root / lot_id
        if d.exists() and d.is_dir():
            parts: list[str] = []
            for f in sorted(d.iterdir()):
                if not f.is_file() or f.suffix.lower() not in {
                    ".docx", ".pdf", ".rtf", ".xlsx", ".xls"
                }:
                    continue
                ed = extract(f)
                if ed.text:
                    parts.append(f"=== {f.name} ===\n\n{ed.text}")
            text = "\n\n".join(parts)
            _text_cache[lot_id] = text
            return text
    _text_cache[lot_id] = ""
    return ""


def _find_with_context(text: str, span: str) -> tuple[str, str, str, bool]:
    """Возвращает (before, match, after, found_exactly).
    found_exactly=False если span не нашёлся дословно (поиск по нормализованной версии)."""
    if not text or not span:
        return "", span, "", False
    idx = text.find(span)
    if idx < 0:
        # Попробуем нормализованный поиск
        norm_text = re.sub(r"\s+", " ", text)
        norm_span = re.sub(r"\s+", " ", span)
        idx_norm = norm_text.find(norm_span)
        if idx_norm < 0:
            return "", span, "", False
        s = max(0, idx_norm - CONTEXT_BEFORE)
        e = min(len(norm_text), idx_norm + len(norm_span) + CONTEXT_AFTER)
        return (
            norm_text[s:idx_norm],
            norm_text[idx_norm:idx_norm + len(norm_span)],
            norm_text[idx_norm + len(norm_span):e],
            False,
        )
    s = max(0, idx - CONTEXT_BEFORE)
    e = min(len(text), idx + len(span) + CONTEXT_AFTER)
    return text[s:idx], text[idx:idx + len(span)], text[idx + len(span):e], True


def main() -> None:
    flags_with_context = []

    for d in REPORTS_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            if p.name == "_summary.json":
                continue
            try:
                report = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue

            tender_id = report["tender_id"]
            full_text = _lot_text(tender_id)

            for flag in report.get("flags", []):
                before, match, after, found_exact = _find_with_context(
                    full_text, flag["span_text"]
                )
                flags_with_context.append({
                    "flag_id": _flag_id(tender_id, flag["label"], flag["span_text"]),
                    "tender_id": tender_id,
                    "label": flag["label"],
                    "section": flag.get("section", ""),
                    "span_text": flag["span_text"],
                    "confidence": flag.get("confidence", 0.0),
                    "rationale": flag.get("rationale", ""),
                    "regulatory_reference": flag.get("regulatory_reference", ""),
                    "context_before": before,
                    "context_match": match,
                    "context_after": after,
                    "found_exact": found_exact,
                    "report_path": str(p.relative_to(ROOT)),
                })

    # JSON-версия (для скриптов)
    json_path = OUT_DIR / "flags_review_pack.json"
    json_path.write_text(
        json.dumps(flags_with_context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Markdown-версия (для чтения)
    md_lines = [
        f"# Flag Review Pack — {len(flags_with_context)} flags",
        "",
        f"Generated from reports in: {[str(d.relative_to(ROOT)) for d in REPORTS_DIRS]}",
        f"Source documents: {[str(d.relative_to(ROOT)) for d in RAW_DIRS]}",
        "",
        f"For each flag: span_text, LLM rationale, regulatory reference, ±{CONTEXT_BEFORE}/{CONTEXT_AFTER} chars of context.",
        "",
        "Verdicts to assign per flag: **TRUE** (real anomaly per codebook) / **FALSE** (false positive) / **PARTIAL** (right idea but wrong label or too broad span).",
        "",
        "---",
        "",
    ]
    for i, f in enumerate(flags_with_context, 1):
        marker = "✓" if f["found_exact"] else "≈"
        md_lines.append(f"## #{i} [{f['label']}] — {f['tender_id']} {marker}")
        md_lines.append("")
        md_lines.append(f"- **flag_id**: `{f['flag_id']}`")
        md_lines.append(f"- **section**: `{f['section']}`")
        md_lines.append(f"- **confidence**: {f['confidence']}")
        md_lines.append(f"- **regulatory_reference**: {f['regulatory_reference']}")
        md_lines.append(f"- **rationale**: {f['rationale']}")
        md_lines.append("")
        md_lines.append("### Span:")
        md_lines.append(f"> «{f['span_text']}»")
        md_lines.append("")
        if f["found_exact"]:
            md_lines.append("### Context (exact match):")
        else:
            md_lines.append("### Context (normalized whitespace match):")
        md_lines.append("```")
        md_lines.append(f"{f['context_before']}【{f['context_match']}】{f['context_after']}")
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path = OUT_DIR / "flags_review_pack.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Stats
    from collections import Counter
    label_counts = Counter(f["label"] for f in flags_with_context)
    not_found = sum(1 for f in flags_with_context if not f["found_exact"])

    print(f"✓ Прочитано {len(flags_with_context)} флагов")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path} ({md_path.stat().st_size // 1024} KB)")
    print(f"  - Span не найден дословно: {not_found}/{len(flags_with_context)}")
    print()
    print("Распределение по меткам:")
    for lbl, n in label_counts.most_common():
        print(f"  {n:3d}  {lbl}")


if __name__ == "__main__":
    main()
