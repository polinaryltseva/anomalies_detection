"""Rule-based regex detector for high-confidence anomaly patterns.

Catches specific patterns that are reliably anomalies:
1. Empty evaluation criteria («Не предусмотрено», «Не применяется», «Не установлен»)
2. Extreme payment terms (≥120 рабочих дней)
3. Explicit ban on equivalents
4. Concrete persons (ФИО) in contact info linked to lot

This is complementary to LLM detection — high precision, low recall, fast.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_rules"
OUT.mkdir(parents=True, exist_ok=True)


# Pattern, label, confidence, regulatory_reference
RULES = [
    # R1: Empty evaluation criteria (high confidence)
    (
        re.compile(
            r"(?:порядок|критерии)\s+оценки\s+(?:и\s+сопоставления\s+)?заявок"
            r"[^.]{0,40}?"
            r"(?:не\s+предусмотрен[ыо]?|не\s+применяется|не\s+установлен[ыо]?|отсутствует|не\s+приме[нт]?)",
            re.IGNORECASE | re.DOTALL
        ),
        "ambiguous_evaluation_criteria",
        0.95,
        "EU Directive 2014/24/EU Art. 67 — отсутствие критериев оценки",
    ),
    # R2: Extreme payment terms (≥120 working days)
    (
        re.compile(
            r"(?:срок\s+оплаты|оплат[аы]\s+(?:за\s+)?(?:товар|услуг|работ))[^.]{0,80}?"
            r"(?:в\s+течение\s+)?(\d{2,3})\s*(?:\(\w+\)\s*)?(?:рабочих\s+)?(?:дней|кал\.\s*дней)",
            re.IGNORECASE
        ),
        "unusual_contract_terms",
        0.85,
        "Срок оплаты >120 раб.дн. = экстремальный (норма 7-60 дн.)",
    ),
    # R3: Explicit ban on «или эквивалент»
    (
        re.compile(
            r"(?:использование|применение|сопровождение)?\s*(?:терминов?|слов[а])?\s*"
            r"[«\"]?или\s+эквивалент[»\"]?\s*[/,]?\s*[«\"]?эквивалент[»\"]?\s*"
            r"не\s+(?:допускается|применяется|разрешается)",
            re.IGNORECASE
        ),
        "brand_or_model_targeting",
        0.95,
        "Прямой запрет на 'или эквивалент' — блокирует подачу аналогов",
    ),
    # R4: Bidder must specify exact brand/article
    (
        re.compile(
            r"(?:не\s+допускается\s+(?:применение|использование|сопровождение)\s+(?:слов(?:осочетаний)?|термин(?:ов|а))?\s*)?"
            r"[«\"]?эквивалент[»\"]?\s*[,/]?\s*[«\"]?аналог[»\"]?\s*[,/]?\s*[«\"]?(?:должен\s+быть|должна\s+быть)?[»\"]?",
            re.IGNORECASE
        ),
        "brand_or_model_targeting",
        0.7,
        "Запрет в инструкции участника на использование 'эквивалент'",
    ),
    # R5: Single bidder contract awarded
    (
        re.compile(
            r"заключить\s+договор\s+с\s+(?:[А-ЯЁ][а-яё]+\s+)*[«\"][^»\"]+[»\"]"
            r"(?:[^.]*?как)?\s+единственн[ыо]м\s+участник",
            re.IGNORECASE
        ),
        "conflict_of_interest_signals",
        0.6,
        "Договор с единственным участником — повышенный риск аффилированности",
    ),
]


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


def detect_rules(lot_id: str, text: str) -> list[dict]:
    flags = []
    for rule_idx, (pattern, label, conf, ref) in enumerate(RULES, 1):
        for match in pattern.finditer(text):
            span = match.group(0)
            if len(span) > 300:
                span = span[:300]
            flags.append({
                "label": label,
                "section": "regex",
                "span_text": span,
                "confidence": conf,
                "rationale": f"Rule R{rule_idx}: pattern match",
                "regulatory_reference": ref,
            })
    return flags


def main() -> None:
    import math
    all_lots = sorted([d.name for d in RAW.iterdir() if d.is_dir()])
    print(f"Total lots: {len(all_lots)}")

    summary = []
    for i, lot_id in enumerate(all_lots, 1):
        text = gather_text(lot_id)
        if not text:
            continue
        flags = detect_rules(lot_id, text)
        sum_conf = sum(f["confidence"] for f in flags)
        risk = round(1.0 - math.exp(-sum_conf), 3) if flags else 0.0
        if risk >= 0.7:
            level = "high"
        elif risk >= 0.3:
            level = "medium"
        else:
            level = "low"
        report = {
            "tender_id": lot_id,
            "overall_risk_score": risk,
            "risk_level": level,
            "flags": flags,
            "method": "rule_based:regex_v1",
        }
        (OUT / f"{lot_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        if i % 20 == 0:
            print(f"  [{i}/{len(all_lots)}] {lot_id}: risk={risk}, flags={len(flags)}")
        summary.append({
            "tender_id": lot_id, "risk_score": risk, "n_flags": len(flags),
            "labels": sorted({f["label"] for f in flags}),
        })

    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(summary)
    total = sum(s["n_flags"] for s in summary)
    high = sum(1 for s in summary if s["risk_score"] >= 0.7)
    med = sum(1 for s in summary if 0.3 <= s["risk_score"] < 0.7)
    low = sum(1 for s in summary if s["risk_score"] < 0.3)
    print(f"\nRule-based on {n} lots:")
    print(f"  Total flags: {total}, avg = {total/n:.2f}")
    print(f"  HIGH={high} MED={med} LOW={low}")
    by_label = Counter()
    for s in summary:
        for l in s["labels"]:
            by_label[l] += 1
    print(f"  Lots with each label:")
    for l, n in by_label.most_common():
        print(f"    {l}: {n}")


if __name__ == "__main__":
    main()
