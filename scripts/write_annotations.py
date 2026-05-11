"""Записывает мои (Claude) ручные вердикты по 123 флагам в
data/labeled/flag_annotations.jsonl.

Решения принимались на основе:
- Кодбука v1.0 (docs/codebook.md)
- Контекста ±800 символов из исходного документа
- Знания стандартных формулировок 223-ФЗ

Главный паттерн в данных: модель over-triggers на стандартные требования
из 223-ФЗ (ст. 3.4 ч. 19.1, ст. 3 ч. 6, ст. 3.2 ч. 15 и т.п.) — большинство
'избыточных документов' и 'непропорциональных требований' это просто
цитирование закона.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data/labeled/flags_review_pack.json"
OUT = ROOT / "data/labeled/flag_annotations.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)


# Vердикты по флагам #1..#123 (порядок как в pack)
# F = FALSE (false positive: standard 223-FZ language or non-anomaly)
# P = PARTIAL (real anomaly, but wrong label or too-broad span)
# T = TRUE (real anomaly correctly identified)
VERDICTS = [
    # 1-10
    "P", "P", "F", "F", "F", "P", "P", "F", "F", "F",
    # 11-20: lot_pitanie + lot_microscope variations of standard language
    "F", "F", "T", "F", "F", "F", "F", "F", "F", "F",
    # 21-30: standard 223-FZ requirements lists, repeated patterns
    "F", "F", "P", "F", "P", "F", "F", "F", "F", "F",
    # 31-40
    "F", "F", "F", "F", "F", "F", "F", "F", "F", "F",
    # 41-50
    "F", "F", "F", "F", "F", "F", "F", "F", "F", "F",
    # 51-60: lot_11 brand-bidder rules + standard
    "F", "F", "F", "F", "F", "P", "F", "F", "F", "F",
    # 61-70
    "F", "F", "F", "F", "F", "F", "F", "F", "F", "F",
    # 71-80
    "F", "F", "F", "F", "F", "F", "F", "F", "F", "F",
    # 81-90: лотов с ФИО экспертов и т.п.
    "F", "F", "F", "F", "F", "F", "P", "P", "F", "F",
    # 91-100: дезинфекция (банковская гарантия 0.1%/день — фин стандарт)
    "F", "F", "F", "F", "F", "F", "P", "P", "F", "F",
    # 101-110: кресла + лаб
    "F", "F", "F", "F", "F", "F", "F", "F", "P", "F",
    # 111-120: микроскоп + мебель
    "F", "F", "F", "F", "F", "F", "F", "F", "F", "F",
    # 121-123: умный_дог
    "F", "F", "F",
]

VERDICT_MAP = {"T": "TRUE", "P": "PARTIAL", "F": "FALSE"}


COMMENTS = {
    # Specific comments for cases that need explanation
    1: "Реальная аномалия — запрет на 'или эквивалент' в заявке участника эффективно блокирует эквиваленты. Но метка 'documentary_burden' не подходит (это не про требуемые документы). Скорее L2 brand-targeting indirect или L1 restrictive_specs.",
    2: "Тот же span что и #1 — модель двойной флаг. Метка 'unusual_contract_terms' тоже неверная — это про правила оформления заявки.",
    3: "Стандартный legal threshold по 223-ФЗ для изменений к малым закупкам (<30 млн).",
    4: "Стандартный legal threshold для изменений в извещении.",
    5: "20 дней на подписание договора — рыночная норма.",
    6: "8 дней на e-аукцион — на грани, но в legal норме (≥7 дней по 223-ФЗ).",
    7: "Реальная процедурная проблема (заказчик может рассмотреть раньше дат), но метка unusual_contract_terms неверна — это процедурная гибкость, не condition контракта.",
    13: "Реальная аномалия: 120 рабочих дней оплата ≈ 6 календарных месяцев. Существенно превышает рыночную практику (30-60 дней).",
    23: "5 кал. дней на отправку подписанного договора — borderline. По 223-ФЗ стандарт 5-10 дней.",
    25: "5 рабочих дней поставки медицинских товаров — borderline для нового участника без склада в регионе.",
    56: "Та же тема что и #1/#2 — запрет 'не более'/'не менее'/'или эквивалент' в заявке. Реальная барьерная практика, но метка restrictive_tech_specs скорее про ТЗ заказчика, не про правила оформления заявки.",
    87: "Сжатые сроки на изготовление и поставку custom-made выставочного оборудования (~3 недели). Borderline.",
    88: "Расторжение в одностороннем порядке без возмещения убытков — реально жёсткое условие, но допустимо по ГК РФ. Borderline.",
    97: "L2 паттерн (бренд+модель Siemens) формально верен, но контекст — обслуживание УЖЕ КУПЛЕННОГО оборудования (с инв. номером). Это L8 (привязка к существующему оборудованию) больше чем L2. Реальное ограничение конкуренции — обслуживать Siemens может только сертиф. сервис.",
    98: "Аналогично #97 — Siemens syngo.via с инв. номером. Сервис существующего ПО.",
    109: "2 рабочих дня старт лабораторных тестов — borderline. Стандарт для лабораторий с capacity, но для нового участника может быть барьером.",
}


def main() -> None:
    flags = json.loads(PACK.read_text(encoding="utf-8"))
    assert len(flags) == len(VERDICTS), f"Mismatch: {len(flags)} flags vs {len(VERDICTS)} verdicts"

    annotations: list[dict] = []
    timestamp = datetime.utcnow().isoformat() + "Z"

    for i, (flag, verdict_code) in enumerate(zip(flags, VERDICTS), start=1):
        verdict = VERDICT_MAP[verdict_code]
        ann = {
            "flag_id": flag["flag_id"],
            "tender_id": flag["tender_id"],
            "label": flag["label"],
            "section": flag["section"],
            "span_text": flag["span_text"],
            "confidence": flag["confidence"],
            "rationale": flag["rationale"],
            "regulatory_reference": flag["regulatory_reference"],
            "verdict": verdict,
            "comment": COMMENTS.get(i, ""),
            "annotated_at": timestamp,
            "annotator": "claude-opus-4-7-via-codebook-v1",
            "review_index": i,
        }
        annotations.append(ann)

    with open(OUT, "w", encoding="utf-8") as f:
        for ann in annotations:
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")

    # Stats
    from collections import Counter
    verdict_counts = Counter(a["verdict"] for a in annotations)
    by_label_verdict: dict[str, Counter] = {}
    for a in annotations:
        by_label_verdict.setdefault(a["label"], Counter())[a["verdict"]] += 1

    print(f"✓ {len(annotations)} annotations written to {OUT}")
    print()
    print("=== Overall verdict distribution ===")
    for v in ("TRUE", "PARTIAL", "FALSE"):
        n = verdict_counts.get(v, 0)
        pct = 100 * n / len(annotations)
        print(f"  {v:8s}  {n:3d}  ({pct:5.1f}%)")
    print()
    print("=== Per-label breakdown ===")
    for label in sorted(by_label_verdict.keys()):
        c = by_label_verdict[label]
        total = sum(c.values())
        t, p, fa = c.get("TRUE", 0), c.get("PARTIAL", 0), c.get("FALSE", 0)
        precision_strict = t / total if total else 0  # only TRUE counts
        precision_lenient = (t + p) / total if total else 0  # TRUE + PARTIAL
        print(
            f"  {label:32s} T={t:2d} P={p:2d} F={fa:2d} | "
            f"prec_strict={precision_strict:.2f}  prec_lenient={precision_lenient:.2f}"
        )

    overall_strict = verdict_counts.get("TRUE", 0) / len(annotations)
    overall_lenient = (verdict_counts.get("TRUE", 0) + verdict_counts.get("PARTIAL", 0)) / len(annotations)
    print()
    print(f"Overall precision (strict, TRUE only):    {overall_strict:.3f}")
    print(f"Overall precision (lenient, TRUE+PARTIAL): {overall_lenient:.3f}")


if __name__ == "__main__":
    main()
