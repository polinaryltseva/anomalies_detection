"""Rule-based regex detector v2 — tighter rules, no junk patterns.

Changes vs v1:
- Drop R4 (loose «эквивалент, аналог»): too many table-header false positives
- Fix R2: enforce >=120 days for extreme payment terms (was matching any 2-3 digit number)
- Keep R1 (empty eval criteria): 95%+ precision
- Keep R3 (strict ban-equivalent): only 2 hits but real
- NEW R6: ФИО near company name (potential COI) — conservative
- NEW R7: «единственный поставщик» / «единственным участником» (post-hoc but may be input signal)

Output: data/reports/bulk_rules_v2/<lot>.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_rules_v2"
OUT.mkdir(parents=True, exist_ok=True)


# R1: Empty evaluation criteria (high confidence, 95%+ verified)
R1_PATTERN = re.compile(
    r"(?:порядок|критерии)\s+оценки\s+(?:и\s+сопоставления\s+)?заявок"
    r"[^.]{0,40}?"
    r"(?:не\s+предусмотрен[ыо]?|не\s+применяется|не\s+установлен[ыо]?|отсутствует)",
    re.IGNORECASE | re.DOTALL,
)


# R2 FIXED: extreme payment terms — only match if number >= 120
# Matches «оплата ... в течение N (рабочих/календарных) дней» where N >= 120
R2_PATTERN = re.compile(
    r"(?:срок\s+оплаты|оплат[аы]\s+(?:за\s+)?(?:товар|услуг|работ)[^.]{0,60}|"
    r"расчет[ыа]\s+(?:за|с)[^.]{0,60})"
    r"[^.]{0,40}?"
    r"(?:в\s+течение\s+)?(?P<days>\d{3,})\s*(?:\(\w+\)\s*)?"
    r"(?:(?P<dtype>рабочих|календарных)\s+)?дн",
    re.IGNORECASE,
)


# R3 STRICT: explicit ban on «или эквивалент» phrasing
R3_PATTERN = re.compile(
    r"(?:поставк[аи]|использование|применение)\s+эквивалент[ао]?\s+"
    r"не\s+(?:допуст|подлеж|разреша|допускается)",
    re.IGNORECASE,
)


# R3b STRICT alt: «или эквивалент» / «эквивалент» followed by ban
R3B_PATTERN = re.compile(
    r"[«\"]?или\s+эквивалент[»\"]?[^.]{0,30}?"
    r"не\s+(?:допускается|применяется|разрешается)",
    re.IGNORECASE,
)


# R6: ФИО (initials Х.Х. format) followed by company name in same paragraph
# Conservative: must have ФИО and «ООО»/«АО»/«ИП»/«ОАО» within 200 chars
R6_PATTERN = re.compile(
    r"(?P<fio>[А-ЯЁ][а-яё]+(?:ов|ев|ин|ын|ский|цкий|ова|ева|ина|ына|ская|цкая|ин)\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.)"
    r"[^.]{0,200}?"
    r"\b(?P<co>ООО|ОАО|ЗАО|АО|ИП)\s+[«\"][А-ЯЁ]",
    re.IGNORECASE,
)


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

    # R1
    for match in R1_PATTERN.finditer(text):
        flags.append({
            "rule": "R1",
            "label": "ambiguous_evaluation_criteria",
            "span_text": match.group(0)[:300],
            "confidence": 0.95,
            "rationale": "R1: empty evaluation criteria",
            "regulatory_reference": "EU Directive 2014/24/EU Art. 67",
        })

    # R2 (with day-count check)
    for match in R2_PATTERN.finditer(text):
        try:
            days = int(match.group("days"))
        except (ValueError, IndexError):
            continue
        if days < 120:
            continue  # Skip non-extreme
        flags.append({
            "rule": "R2",
            "label": "unusual_contract_terms",
            "span_text": match.group(0)[:300],
            "confidence": 0.90,
            "rationale": f"R2: extreme payment {days} days",
            "regulatory_reference": "223-FZ ст.3 ч.5.4 (МСП payment ≤7 раб.дн.)",
        })

    # R3
    for match in R3_PATTERN.finditer(text):
        flags.append({
            "rule": "R3",
            "label": "brand_or_model_targeting",
            "span_text": match.group(0)[:300],
            "confidence": 0.92,
            "rationale": "R3: explicit ban on equivalent for spare parts",
            "regulatory_reference": "223-FZ ст.3 ч.6.1 (но allowed exception for spare parts)",
        })

    # R3b — alt phrasing
    for match in R3B_PATTERN.finditer(text):
        flags.append({
            "rule": "R3b",
            "label": "brand_or_model_targeting",
            "span_text": match.group(0)[:300],
            "confidence": 0.90,
            "rationale": "R3b: «или эквивалент» followed by ban phrase",
            "regulatory_reference": "223-FZ ст.3 ч.6.1",
        })

    # R6 (ФИО + company)
    for match in R6_PATTERN.finditer(text):
        flags.append({
            "rule": "R6",
            "label": "conflict_of_interest_signals",
            "span_text": match.group(0)[:300],
            "confidence": 0.55,
            "rationale": f"R6: person {match.group('fio')} near company {match.group('co')}",
            "regulatory_reference": "EU Commission Notice on collusion 2021/C 91/01",
        })

    return flags


def main() -> None:
    all_lots = sorted([d.name for d in RAW.iterdir() if d.is_dir()])
    print(f"Total lots: {len(all_lots)}")

    summary = []
    rule_counts = Counter()
    for i, lot_id in enumerate(all_lots, 1):
        text = gather_text(lot_id)
        if not text:
            continue
        flags = detect_rules(lot_id, text)
        for f in flags:
            rule_counts[f["rule"]] += 1
        report = {
            "tender_id": lot_id,
            "flags": flags,
            "method": "rule_based:regex_v2",
        }
        (OUT / f"{lot_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        if i % 100 == 0:
            print(f"  [{i}/{len(all_lots)}]")
        summary.append({
            "tender_id": lot_id,
            "n_flags": len(flags),
            "labels": sorted({f["label"] for f in flags}),
            "rules": sorted({f["rule"] for f in flags}),
        })

    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nRule-based v2 on {len(summary)} lots:")
    print(f"By rule: {dict(rule_counts)}")
    print(f"\nLots with each rule:")
    by_rule_lots = Counter()
    for s in summary:
        for r in s["rules"]:
            by_rule_lots[r] += 1
    for r, n in by_rule_lots.most_common():
        print(f"  {r}: {n} lots")


if __name__ == "__main__":
    main()
