# -*- coding: utf-8 -*-
"""Подготовка review pack для 13 LOW-лотов FT v3a (held-out).

Для каждого лота:
1. Извлекает полный текст всех файлов
2. Сегментирует на разделы
3. Прогоняет rule_detector_v2 (R1, R2, R3, R3b, R6)
4. Извлекает potentially suspicious фрагменты по эвристикам:
   - brand-капсы (последовательности заглавных латинских в текста)
   - артикулы / SKU паттерны
   - подозрительные сроки
   - "не предусмотрено" / "не применяется"
   - ФИО + ООО в одном предложении
5. Сохраняет review pack в markdown + JSON

Output:
  data/labeled/heldout_low_review_pack.md
  data/labeled/heldout_low_review_pack.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

LOW_LOTS = [
    "146458294", "148192417", "150132934",
    "169515437", "169548175", "169568334",
    "169596403", "169596693", "169633471",
    "171693502", "171740008", "171750885", "171838096",
]

RAW = ROOT / "data/raw/bulk"
OUT_MD = ROOT / "data/labeled/heldout_low_review_pack.md"
OUT_JSON = ROOT / "data/labeled/heldout_low_review_pack.json"

# --- Rule patterns (v2) ---
R1_PATTERN = re.compile(
    r"(?:порядок|критерии)\s+оценки\s+(?:и\s+сопоставления\s+)?заявок"
    r"[^.]{0,40}?"
    r"(?:не\s+предусмотрен[ыо]?|не\s+применяется|не\s+установлен[ыо]?|отсутствует)",
    re.IGNORECASE | re.DOTALL,
)
R2_PATTERN = re.compile(
    r"(?:срок\s+оплаты|оплат[аы]\s+(?:за\s+)?(?:товар|услуг|работ)[^.]{0,60}|"
    r"расчет[ыа]\s+(?:за|с)[^.]{0,60})"
    r"[^.]{0,40}?"
    r"(?:в\s+течение\s+)?(?P<days>\d{3,})\s*(?:\(\w+\)\s*)?"
    r"(?:(?P<dtype>рабочих|календарных)\s+)?дн",
    re.IGNORECASE,
)
R3_PATTERN = re.compile(
    r"(?:поставк[аи]|использование|применение)\s+эквивалент[ао]?\s+"
    r"не\s+(?:допуст|подлеж|разреша|допускается)",
    re.IGNORECASE,
)
R3B_PATTERN = re.compile(
    r'[«"]?или\s+эквивалент[»"]?[^.]{0,30}?'
    r"не\s+(?:допускается|применяется|разрешается)",
    re.IGNORECASE,
)
R6_PATTERN = re.compile(
    r"(?P<fio>[А-ЯЁ][а-яё]+(?:ов|ев|ин|ын|ский|цкий|ова|ева|ина|ына|ская|цкая)\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)"
    r"[^.]{0,200}?"
    r"\b(?P<co>ООО|ОАО|ЗАО|АО|ИП)\s+[«\"][А-ЯЁ]",
    re.IGNORECASE,
)

# --- Heuristic patterns for suspicious fragments ---

# Brand-like capsule: 2+ заглавных латинских (LATIN) + опционально цифры
BRAND_LATIN = re.compile(r"\b[A-Z][A-Z0-9-]{2,}(?:\s+[A-Z0-9][A-Z0-9-]+)*\b")

# Article / SKU: цифры + дефисы + буквы (например, X-1234-AB)
SKU_PATTERN = re.compile(r"\b[A-ZА-Я0-9]+-[A-ZА-Я0-9-]+\b")

# Точные числовые требования вида "не менее 1280×800"
EXACT_DIM = re.compile(r"\b\d+\s*[×x]\s*\d+\b")

# Короткие сроки в днях (1-9 дней)
SHORT_DAYS = re.compile(
    r"\b(?:в\s+течение\s+)?(?:[1-9])\s*(?:\(\w+\)\s*)?(?:рабочих|календарных)?\s*дн",
    re.IGNORECASE,
)

# Слово "эквивалент" с контекстом ±100 chars
EQUIV_CTX = re.compile(r".{0,80}эквивалент.{0,80}", re.IGNORECASE | re.DOTALL)


def gather_sections(lot_id: str) -> dict[str, str]:
    d = RAW / lot_id
    if not d.exists():
        return {}
    parts = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {
            ".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"
        }:
            continue
        ed = extract(f)
        if ed.text:
            parts.append(f"\n\n=== {f.name} ===\n\n{ed.text}")
    full = "\n".join(parts)
    sections = merge_sections(segment(full))
    if not sections:
        sections = {"unsegmented": full}
    return sections


def detect_rules(text: str) -> list[dict[str, str]]:
    hits = []
    for label, pat in [
        ("R1 empty_eval", R1_PATTERN),
        ("R3 strict_ban", R3_PATTERN),
        ("R3b alt_ban", R3B_PATTERN),
        ("R6 fio_ooo", R6_PATTERN),
    ]:
        for m in pat.finditer(text):
            hits.append({"rule": label, "match": m.group(0)[:300]})
    for m in R2_PATTERN.finditer(text):
        try:
            days = int(m.group("days"))
        except (ValueError, IndexError):
            continue
        if days >= 120:
            hits.append({"rule": f"R2 extreme_payment ({days}d)", "match": m.group(0)[:300]})
    return hits


def extract_suspicious_fragments(sections: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "brand_latin": [],
        "sku_like": [],
        "exact_dimensions": [],
        "short_days": [],
        "equivalent_ctx": [],
    }
    relevant = {k: v for k, v in sections.items() if k in ("tz", "pricing", "evaluation", "requirements", "contract")}
    for sec_name, text in relevant.items():
        # Brand-like capsules: only those with >=4 chars, drop common abbreviations
        seen_brands = set()
        for m in BRAND_LATIN.finditer(text):
            t = m.group(0)
            if len(t) < 4:
                continue
            if t in {"PDF", "DOCX", "XLSX", "USB", "HDD", "SSD", "RAM", "CPU", "OS",
                     "TCP", "IP", "HTTP", "URL", "API", "JSON", "XML", "GPS"}:
                continue
            if t in seen_brands:
                continue
            seen_brands.add(t)
            ctx = max(0, m.start() - 60)
            out["brand_latin"].append(f"[{sec_name}] {text[ctx:m.end()+60]}")
            if len(out["brand_latin"]) >= 30:
                break

        for m in SKU_PATTERN.finditer(text):
            t = m.group(0)
            if len(t) < 6 or t.replace("-", "").isdigit():
                continue
            ctx = max(0, m.start() - 40)
            snippet = text[ctx:m.end()+40]
            if any(snippet.startswith(p) for p in ["[", "{"]):
                continue
            out["sku_like"].append(f"[{sec_name}] {snippet}")
            if len(out["sku_like"]) >= 15:
                break

        for m in EXACT_DIM.finditer(text):
            ctx = max(0, m.start() - 40)
            out["exact_dimensions"].append(f"[{sec_name}] {text[ctx:m.end()+40]}")
            if len(out["exact_dimensions"]) >= 10:
                break

        for m in SHORT_DAYS.finditer(text):
            ctx = max(0, m.start() - 60)
            out["short_days"].append(f"[{sec_name}] {text[ctx:m.end()+60]}")
            if len(out["short_days"]) >= 10:
                break

        for m in EQUIV_CTX.finditer(text):
            out["equivalent_ctx"].append(f"[{sec_name}] {m.group(0)}")
            if len(out["equivalent_ctx"]) >= 8:
                break

    # Дедупликация
    for k in out:
        seen = set()
        unique = []
        for s in out[k]:
            key = s.strip()[:200]
            if key in seen:
                continue
            seen.add(key)
            unique.append(s)
        out[k] = unique[:15]
    return out


def main() -> None:
    md_lines = []
    md_lines.append("# Held-out review pack: 13 LOW-лотов FT v3a\n")
    md_lines.append("Подготовлен для secondary annotation pass.\n")
    md_lines.append("Цель: для каждого лота определить, действительно ли в тексте отсутствуют ")
    md_lines.append("реальные нарушения по codebook v3 (L1-L8) с учётом whitelist W1-W15. ")
    md_lines.append("Verdict-кодировка: `clean` / `missed_TRUE` / `missed_PARTIAL`.\n")
    md_lines.append("---\n")

    json_data = []

    for i, lot_id in enumerate(LOW_LOTS, 1):
        print(f"[{i}/{len(LOW_LOTS)}] Processing lot {lot_id}...")
        sections = gather_sections(lot_id)
        if not sections:
            print(f"  WARN: no text for {lot_id}")
            continue

        full_text = "\n\n".join(sections.values())
        rule_hits = detect_rules(full_text)
        suspicious = extract_suspicious_fragments(sections)

        section_summary = {k: len(v) for k, v in sections.items()}

        json_data.append({
            "lot_id": lot_id,
            "section_chars": section_summary,
            "rule_hits": rule_hits,
            "suspicious_fragments": suspicious,
        })

        md_lines.append(f"## Лот {lot_id}\n")
        md_lines.append(f"**Разделы:** {', '.join(f'{k} ({v} chars)' for k, v in section_summary.items())}\n")

        if rule_hits:
            md_lines.append(f"\n### Rule-based hits ({len(rule_hits)})\n")
            for hit in rule_hits:
                md_lines.append(f"- **{hit['rule']}**: `{hit['match'][:200]}`\n")
        else:
            md_lines.append("\n### Rule-based hits: НЕТ\n")

        md_lines.append("\n### Эвристически подозрительные фрагменты\n")
        for cat, items in suspicious.items():
            if not items:
                continue
            md_lines.append(f"\n**{cat}** ({len(items)}):\n")
            for s in items[:8]:
                clean_s = s.replace("\n", " ").replace("\r", " ")
                clean_s = re.sub(r"\s+", " ", clean_s).strip()
                md_lines.append(f"- {clean_s[:300]}\n")

        # Beginning of TZ section (most informative)
        if "tz" in sections:
            md_lines.append("\n### Начало раздела tz (первые 2000 chars)\n")
            md_lines.append("```\n")
            md_lines.append(sections["tz"][:2000].replace("\n\n\n", "\n\n"))
            md_lines.append("\n```\n")
        elif "unsegmented" in sections:
            md_lines.append("\n### Начало unsegmented (первые 2000 chars)\n")
            md_lines.append("```\n")
            md_lines.append(sections["unsegmented"][:2000].replace("\n\n\n", "\n\n"))
            md_lines.append("\n```\n")

        md_lines.append("\n---\n")

    OUT_MD.write_text("".join(md_lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReview pack: {OUT_MD}")
    print(f"JSON: {OUT_JSON}")


if __name__ == "__main__":
    main()
