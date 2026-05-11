"""Авто-разметка v2 флагов через **те же rule-based heuristics** что использовались
вручную для v1 (whitelist W1-W10).

Это позволяет сравнить v1 (предыдущая ручная разметка 121 флага) с v2
(автоматическая по тем же правилам). Результат — приближённая оценка precision.
Для финального VKR можно потом ручно перепроверить spot-check.

Heuristics реализованы как Python-предикаты на span_text + context.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

V2_DIR = ROOT / "data/reports/bulk_v2"
RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/labeled/bulk_v2_annotations.jsonl"

CONTEXT = 800
_text_cache: dict[str, str] = {}


def lot_text(lot_id: str) -> str:
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
            parts.append(ed.text)
    text = "\n\n".join(parts)
    _text_cache[lot_id] = text
    return text


def find_context(full: str, span: str) -> str:
    if not full or not span:
        return ""
    idx = full.find(span)
    if idx < 0:
        norm_text = re.sub(r"\s+", " ", full)
        norm_span = re.sub(r"\s+", " ", span)
        idx = norm_text.find(norm_span)
        if idx < 0:
            return ""
        full = norm_text
    s = max(0, idx - CONTEXT)
    e = min(len(full), idx + len(span) + CONTEXT)
    return full[s:e]


# Whitelist heuristics — каждая возвращает (matched, rule_id) или (False, "")

W_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("W1_anti_coi",
     re.compile(r"(отсутствие|отсутствия)\s+(?:между\s+)?(?:участником|участников)?\s*(?:закупки|процедуры закупки)?\s*(?:и\s+(?:заказчиком|заказчика))?\s*конфликта\s+интересов",
                re.IGNORECASE)),
    ("W1_coi_definition",
     re.compile(r"(?:под\s+которым\s+понимаются\s+случаи|состоят\s+в\s+браке\s+с\s+физическими\s+лицами|являющимися\s+выгодоприобретателями)",
                re.IGNORECASE)),
    ("W2_smsp_only",
     re.compile(r"только\s+субъекты\s+(?:малого|малого\s+и\s+среднего)\s+предпринимательства",
                re.IGNORECASE)),
    ("W2_smsp_eng",
     re.compile(r"\bсмп[\s-]?only\b|только\s+смп\b", re.IGNORECASE)),
    ("W3_russian_origin",
     re.compile(r"(российского\s+происхождения|товаров?\s+иностранного\s+государства|нац(?:иональн)?\.?\s*режим|приоритет.*российск|преимуществ.*российск)",
                re.IGNORECASE)),
    ("W4_5day_signing",
     re.compile(r"(?:в\s+течение\s+)?[35]\s*\(\s*[трехти]+\s*\)\s+(?:рабочих\s+)?дней?.*(?:с|со)\s+(?:дат[ыеа]|момента)\s+(?:размещения|получения|направления|подписания)\s*(?:заказчиком\s+)?(?:на\s+электронной\s+площадке\s+)?проекта\s+договора",
                re.IGNORECASE)),
    ("W4_4day_modification",
     re.compile(r"4\s*\(\s*четыре[хм]?\s*\)\s+дн", re.IGNORECASE)),
    ("W4_25_tax",
     re.compile(r"25\s*%.*(?:балансовой\s+стоимости|активов\s+участника|задолженности\s+по\s+(?:налогам|сборам))",
                re.IGNORECASE)),
    ("W5_or_equivalent_50chars", None),  # custom check below
    ("W6_vehicle_id",
     re.compile(r"(?:VIN|гос[\.\s]?№|госномер|инв[\.\s]?№|инвентарный\s+номер|год\s+выпуска)",
                re.IGNORECASE)),
    ("W6_existing_equipment",
     re.compile(r"(имеющийся\s+у\s+заказчика|используем(?:ом|ого|ыми)\s+заказчиком|на\s+оборудовании.*заказчик)",
                re.IGNORECASE)),
    ("W7_compatibility",
     re.compile(r"(совместим(?:ость|о|ы)\s+с\s+имеющимся|обеспечения\s+взаимодействия|необходимости\s+обеспечения)",
                re.IGNORECASE)),
    ("W8_meta_legal_brand",
     re.compile(r"(?:указани[ея]|содержит\s+указание)\s+на\s+товарный\s+знак\s*\(?(?:при\s+наличии|его\s+словесное)",
                re.IGNORECASE)),
    ("W9_standard_qualification",
     re.compile(r"(?:реестр(?:е|а)?\s+недобросовестных\s+поставщиков|отсутствие\s+судимости\s+по\s+ст\.?\s*289|иностранн(?:ого|ым)\s+агент(?:а|ом)|правомочности?\s+подписания)",
                re.IGNORECASE)),
    ("W10_auction_price",
     re.compile(r"(?:аукцион(?:а|е)?\s+в\s+электронной\s+форме|критери(?:й|и)\s+(?:оценки|сопоставления)|информационной\s+карте)",
                re.IGNORECASE)),
]


def check_whitelist(span: str, context: str, label: str) -> tuple[bool, str]:
    """Возвращает (попадает в whitelist, rule)."""
    full = (context or span)
    span_low = span.lower()
    full_low = full.lower()

    # W5 special: brand+«или эквивалент» в пределах 50 символов
    if label == "brand_or_model_targeting":
        # Поиск «или эквивалент» в пределах ±50 символов от span в context
        equiv_pat = re.compile(r"(или\s+эквивалент|или\s+аналог|или\s+иной\s+эквивалент)", re.IGNORECASE)
        idx = full_low.find(span_low)
        if idx >= 0:
            window_start = max(0, idx - 50)
            window_end = min(len(full), idx + len(span) + 50)
            window = full[window_start:window_end]
            if equiv_pat.search(window):
                return True, "W5_or_equivalent_50chars"

    # Other patterns
    for rule_id, pat in W_PATTERNS:
        if pat is None:
            continue
        # Only check W1 if label is COI
        if rule_id.startswith("W1_") and label != "conflict_of_interest_signals":
            continue
        # W2 SMSP — only if label is COI/disprop_qual/brand
        if rule_id.startswith("W2_") and label not in {
            "conflict_of_interest_signals", "disproportionate_qualification", "brand_or_model_targeting",
        }:
            continue
        # W4 sub-rules — only relevant labels
        if rule_id == "W4_5day_signing" and label != "unusual_short_deadlines":
            continue
        if rule_id == "W4_25_tax" and label != "disproportionate_qualification":
            continue
        if rule_id == "W6_vehicle_id" and label not in {"brand_or_model_targeting", "restrictive_tech_specs"}:
            continue
        if rule_id == "W7_compatibility" and label not in {"brand_or_model_targeting", "conflict_of_interest_signals"}:
            continue
        if rule_id == "W8_meta_legal_brand" and label != "brand_or_model_targeting":
            continue
        if rule_id == "W9_standard_qualification" and label not in {
            "disproportionate_qualification", "documentary_burden",
        }:
            continue
        if rule_id == "W10_auction_price" and label != "ambiguous_evaluation_criteria":
            continue

        # Span match
        if pat.search(span):
            return True, rule_id
        # Context match (broader)
        if pat.search(full):
            return True, rule_id

    return False, ""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    reports = sorted(V2_DIR.glob("*.json"))
    reports = [r for r in reports if r.name != "_summary.json"]
    print(f"v2 reports: {len(reports)}")

    rows = []
    for p in reports:
        r = json.loads(p.read_text(encoding="utf-8"))
        tender_id = r["tender_id"]
        full = lot_text(tender_id)
        for f in r["flags"]:
            ctx = find_context(full, f["span_text"])
            wl, rule = check_whitelist(f["span_text"], ctx, f["label"])
            verdict = "FALSE_W" if wl else "MAYBE_TRUE"
            rows.append({
                "tender_id": tender_id,
                "label": f["label"],
                "section": f["section"],
                "span": f["span_text"][:200],
                "confidence": f.get("confidence", 0),
                "auto_verdict": verdict,
                "wl_rule": rule,
                "lot_risk": r["overall_risk_score"],
            })

    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Stats
    print(f"\nTotal v2 flags: {len(rows)}")
    verdicts = Counter(r["auto_verdict"] for r in rows)
    print(f"Auto verdicts: {dict(verdicts)}")

    # By label
    by_label = defaultdict(Counter)
    for r in rows:
        by_label[r["label"]][r["auto_verdict"]] += 1
    print("\nBy label:")
    for lbl in sorted(by_label):
        c = by_label[lbl]
        n = sum(c.values())
        maybe = c.get("MAYBE_TRUE", 0)
        false_w = c.get("FALSE_W", 0)
        print(f"  {lbl}: MAYBE_TRUE={maybe} FALSE_W={false_w}  precision_upper={100*maybe/n:.1f}%")

    # Whitelist rules triggered
    rule_counts = Counter(r["wl_rule"] for r in rows if r["wl_rule"])
    print("\nWhitelist triggers:")
    for rule, n in rule_counts.most_common():
        print(f"  {rule}: {n}")

    print(f"\nWritten -> {OUT}")


if __name__ == "__main__":
    main()
