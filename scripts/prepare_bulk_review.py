"""Стратифицированная выборка флагов из 200-лотового bulk run для ручной разметки.

Стратегия:
1. ВСЕ флаги из bottom-10 лотов (risk < 0.7) — нужно понять почему низкий risk
2. ВСЕ brand_or_model_targeting (81) — лучшая метка по прежним данным, проверяем precision
3. Random sample 30 из conflict_of_interest_signals (108) — выросла вдвое, проверяем
4. Random sample 10 из top-3 лотов с risk=1.0 — error analysis cases

Выход: tests/fixtures/bulk_review_pack.{json,md}
"""

from __future__ import annotations

import json
import random
import re
import sys
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

REPORTS = ROOT / "data/reports/bulk"
RAW = ROOT / "data/raw/bulk"
OUT_DIR = ROOT / "data/labeled"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONTEXT = 800
random.seed(42)


def _flag_id(tender_id: str, label: str, span: str) -> str:
    return md5(f"{tender_id}|{label}|{span[:200]}".encode()).hexdigest()[:16]


_text_cache: dict[str, str] = {}


def _lot_text(lot_id: str) -> str:
    if lot_id in _text_cache:
        return _text_cache[lot_id]
    d = RAW / lot_id
    if not d.exists():
        _text_cache[lot_id] = ""
        return ""
    parts: list[str] = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}:
            continue
        ed = extract(f)
        if ed.text:
            parts.append(f"=== {f.name} ===\n\n{ed.text}")
    text = "\n\n".join(parts)
    _text_cache[lot_id] = text
    return text


def _find_with_context(text: str, span: str) -> tuple[str, str, str, bool]:
    if not text or not span:
        return "", span, "", False
    idx = text.find(span)
    if idx < 0:
        norm_text = re.sub(r"\s+", " ", text)
        norm_span = re.sub(r"\s+", " ", span)
        idx_norm = norm_text.find(norm_span)
        if idx_norm < 0:
            return "", span, "", False
        s = max(0, idx_norm - CONTEXT)
        e = min(len(norm_text), idx_norm + len(norm_span) + CONTEXT)
        return (
            norm_text[s:idx_norm],
            norm_text[idx_norm:idx_norm + len(norm_span)],
            norm_text[idx_norm + len(norm_span):e],
            False,
        )
    s = max(0, idx - CONTEXT)
    e = min(len(text), idx + len(span) + CONTEXT)
    return text[s:idx], text[idx:idx + len(span)], text[idx + len(span):e], True


def _build_flag_record(report: dict, flag: dict, sample_group: str) -> dict:
    full_text = _lot_text(report["tender_id"])
    before, match, after, found_exact = _find_with_context(full_text, flag["span_text"])
    return {
        "flag_id": _flag_id(report["tender_id"], flag["label"], flag["span_text"]),
        "tender_id": report["tender_id"],
        "lot_risk_score": report["overall_risk_score"],
        "lot_risk_level": report["risk_level"],
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
        "sample_group": sample_group,
    }


def main() -> None:
    # Загружаем все отчёты
    all_reports: list[dict] = []
    for p in sorted(REPORTS.glob("*.json")):
        if p.name == "_summary.json":
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("flags"):
                all_reports.append(r)
        except Exception:
            continue
    print(f"Loaded {len(all_reports)} reports with flags")

    # 1. Bottom-10 лотов (risk < 0.7) — все их флаги
    bottom = sorted(all_reports, key=lambda r: r["overall_risk_score"])[:10]
    bottom_set = {r["tender_id"] for r in bottom}
    print(f"Bottom-10 lots (risk < {bottom[-1]['overall_risk_score']:.2f})")

    # 2. Все brand_or_model_targeting
    # 3. Random 30 из conflict_of_interest_signals
    # 4. Top-3 лотов — sample 10 флагов

    pool: list[dict] = []

    # Bottom flags
    for r in bottom:
        for f in r["flags"]:
            pool.append(_build_flag_record(r, f, "bottom_10"))

    # Все brand
    brand_flags = []
    for r in all_reports:
        for f in r["flags"]:
            if f["label"] == "brand_or_model_targeting":
                brand_flags.append(_build_flag_record(r, f, "brand_targeting_all"))
    pool.extend(brand_flags)
    print(f"brand_or_model_targeting flags: {len(brand_flags)}")

    # COI sample 30 (random)
    coi_flags_all = []
    for r in all_reports:
        for f in r["flags"]:
            if f["label"] == "conflict_of_interest_signals":
                coi_flags_all.append((r, f))
    random.shuffle(coi_flags_all)
    coi_sample = coi_flags_all[:30]
    pool.extend(_build_flag_record(r, f, "coi_sample_30") for r, f in coi_sample)
    print(f"conflict_of_interest_signals total: {len(coi_flags_all)}, sample: {len(coi_sample)}")

    # Top-3 лотов: каждое 5 случайных флагов
    top3 = sorted(all_reports, key=lambda r: -r["overall_risk_score"])[:3]
    top3 = sorted(top3, key=lambda r: -len(r["flags"]))
    for r in top3[:3]:
        flags = list(r["flags"])
        random.shuffle(flags)
        for f in flags[:5]:
            pool.append(_build_flag_record(r, f, "top_3_sample"))
    print(f"Top-3 sample flags: {sum(min(5, len(r['flags'])) for r in top3[:3])}")

    # Дедуп по flag_id (один и тот же флаг мог попасть в две группы)
    seen = set()
    unique = []
    for rec in pool:
        if rec["flag_id"] in seen:
            continue
        seen.add(rec["flag_id"])
        unique.append(rec)
    print(f"\nTotal flags after dedup: {len(unique)}")

    by_group = {}
    for r in unique:
        by_group.setdefault(r["sample_group"], 0)
        by_group[r["sample_group"]] += 1
    print(f"By group: {by_group}")

    # Save JSON
    json_out = OUT_DIR / "bulk_review_pack.json"
    json_out.write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {json_out}")

    # Save Markdown
    lines = [
        f"# Bulk Review Pack — {len(unique)} flags",
        "",
        "Strategy: stratified sample from 200-lot bulk run (gpt-4o-mini, 191 lots analyzed, 1029 flags).",
        "",
        "Groups:",
    ]
    for g, n in by_group.items():
        lines.append(f"- **{g}**: {n}")
    lines.extend(["", "---", ""])

    for i, f in enumerate(unique, 1):
        marker = "✓" if f["found_exact"] else "≈"
        lines.append(f"## #{i} [{f['label']}] — {f['tender_id']} {marker}  ({f['sample_group']})")
        lines.append("")
        lines.append(f"- **flag_id**: `{f['flag_id']}`")
        lines.append(f"- **lot_risk**: {f['lot_risk_score']:.2f} ({f['lot_risk_level']})")
        lines.append(f"- **section**: `{f['section']}`")
        lines.append(f"- **confidence**: {f['confidence']}")
        lines.append(f"- **rationale**: {f['rationale']}")
        lines.append(f"- **regulatory_reference**: {f['regulatory_reference']}")
        lines.append("")
        lines.append("### Span:")
        lines.append(f"> «{f['span_text']}»")
        lines.append("")
        lines.append("### Context:")
        lines.append("```")
        lines.append(f"{f['context_before']}【{f['context_match']}】{f['context_after']}")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    md_out = OUT_DIR / "bulk_review_pack.md"
    md_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown: {md_out} ({md_out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
