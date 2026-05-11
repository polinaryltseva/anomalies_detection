"""Write verdicts for 128 flags from v3_review_pack."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/labeled/v3_flag_annotations.jsonl"
PACK = json.loads((ROOT / "data/labeled/v3_review_pack.json").read_text(encoding="utf-8"))


# Verdicts indexed by flag # (1-128) — based on systematic codebook v3 (W1-W15) review
VERDICTS: dict[int, tuple[str, str]] = {
    1: ("FALSE", "Generic category 'Поставка строительных материалов' — not brand"),
    2: ("FALSE", "10-20 days for contract = standard 223-FZ ст.3.2 ч.15 (W4)"),
    3: ("FALSE", "Framework contract delivery via Заявки Покупателя — common pattern"),
    4: ("PARTIAL", "30-60 days payment after delivery — borderline, longer than 30-day standard but within commercial range"),
    5: ("FALSE", "Just the contract price (406k RUB) — no qualification requirement"),
    6: ("FALSE", "Documentation request 2 days before deadline = standard procedure"),
    7: ("FALSE", "Generic service 'техническое обслуживание автомобилей' — not brand"),
    8: ("FALSE", "Generic service 'охранные услуги' — not brand"),
    9: ("FALSE", "Запчасти под имеющееся оборудование = legal exception per 223-ФЗ ч.6.1 ст.3 (no equivalent required for spare parts to existing equipment)"),
    10: ("FALSE", "Outcome (single bidder) — not text-based requirement (W7)"),
    11: ("FALSE", "10-20 days for contract = standard 223-FZ ст.3.2 ч.15 (W4)"),
    12: ("FALSE", "Has '(или эквивалент)' clause — escape hatch present"),
    13: ("FALSE", "Just date '16.04.2026' — no measure of how short"),
    14: ("FALSE", "Standard 'Заказчик принимает решение о допуске' (W12)"),
    15: ("FALSE", "ППУ изоляции — standard construction technology, not brand"),
    16: ("PARTIAL", "5 раб.дн. передачи — fragment, depends on item type"),
    17: ("FALSE", "Generic theatre items (занавес, арлекин, кулиса, падуга, задник) — not brand"),
    18: ("FALSE", "Generic category 'расходные материалы для микробиологии' — not brand"),
    19: ("FALSE", "verbatim 25% tax threshold (W4)"),
    20: ("FALSE", "Price recalculation formula — not tech spec"),
    21: ("FALSE", "Generic 'соответствовать требованиям нормативно-технических документов'"),
    22: ("FALSE", "Just bid deadline date — no measure"),
    23: ("FALSE", "Description of medical equipment repair procedure — not tech spec"),
    24: ("FALSE", "Standard refusal procedure (W12)"),
    25: ("FALSE", "Generic medical device category"),
    26: ("FALSE", "Reference to ФГИС реестр медизделий — standard"),
    27: ("PARTIAL", "Biapenem INN (not товарный знак) — for medical procurement borderline; INN allowed by law"),
    28: ("FALSE", "Generic 'по начальным единичным расценкам'"),
    29: ("FALSE", "Standard committee decision procedure (W12)"),
    30: ("FALSE", "Meta reference to TZ"),
    31: ("FALSE", "Generic 'шезлонгов' — furniture category, not brand"),
    32: ("FALSE", "ОКПД2 code + generic dimensions (Не менее…не более) — not brand targeting"),
    33: ("FALSE", "Standard contract security forms — not brand-related"),
    34: ("FALSE", "Standard uklonenie procedure (W12)"),
    35: ("FALSE", "Just label 'Медико-техническое задание'"),
    36: ("FALSE", "Outcome (single ИП participant) — not requirement (W7)"),
    37: ("FALSE", "Generic 'канцелярских товаров' — category, not brand"),
    38: ("FALSE", "Meta reference to Приложение №3 — not a spec itself"),
    39: ("FALSE", "10 months residual shelf life — standard medical procurement"),
    40: ("TRUE", "REAL: «Критерии оценки заявок | Не установлены» + «Порядок | Не установлен»"),
    41: ("FALSE", "10-20 days for contract = standard 223-FZ (W4)"),
    42: ("FALSE", "Anti-corruption rule (no post-tender contract changes) = defensive (W13)"),
    43: ("FALSE", "Meta reference to часть V проекта договора"),
    44: ("FALSE", "Generic 'клей хирургический' — medical category"),
    45: ("FALSE", "Just contract end date — not unusual"),
    46: ("FALSE", "Antidumping rule (1.5x security at 25% lower price) = standard 223-FZ ст.3.4 ч.27 (W4)"),
    47: ("FALSE", "verbatim 25% tax threshold (W4)"),
    48: ("FALSE", "8 days submission window — within 7-15 day MSP norm"),
    49: ("FALSE", "Standard auction win procedure (lowest price)"),
    50: ("FALSE", "'лицензия: Не применяются' = no license needed (W6)"),
    51: ("FALSE", "Just quantity 'веб-камера – 2 штуки'"),
    52: ("FALSE", "10 days for contract signing = standard 223-FZ (W4)"),
    53: ("FALSE", "Just bid ranking output — not eval criteria gap"),
    54: ("FALSE", "Standard 'no scratches/dents' for new goods"),
    55: ("FALSE", "Cultural heritage object (адрес работ) — not brand"),
    56: ("FALSE", "3 days notification of bank details change — standard"),
    57: ("FALSE", "Standard 'товар новый' requirement"),
    58: ("FALSE", "Standard substitution clause (improved characteristics)"),
    59: ("FALSE", "10-20 days for contract = standard 223-FZ (W4)"),
    60: ("FALSE", "Just header 'Члены комиссии' — no actual ФИО captured"),
    61: ("TRUE", "REAL: «Поставка машины направленного бурения УМ-35» — specific model without 'или эквивалент'"),
    62: ("FALSE", "6 months residual shelf life — standard medical"),
    63: ("FALSE", "ОСАГО per vehicle — insurance, not tech spec"),
    64: ("FALSE", "RTS-tender ETP URL — accredited 223-FZ platform"),
    65: ("FALSE", "Заказчик's deputy doctor — standard contact (per codebook FALSE example)"),
    66: ("FALSE", "Standard tie-breaker (earliest bid wins) for аукцион"),
    67: ("FALSE", "verbatim 25% tax threshold (W4)"),
    68: ("TRUE", "REAL: «Порядок оценки и сопоставления заявок | Не предусмотрено» — empty eval"),
    69: ("FALSE", "Generic 'стальных труб' — commodity"),
    70: ("FALSE", "Standard fence mesh dimensions (ГОСТ-style)"),
    71: ("FALSE", "Standard rule: bid security not returned on uklonenie"),
    72: ("FALSE", "Standard rejection grounds (liquidation, bankruptcy)"),
    73: ("FALSE", "Just table header 'Характеристики товара'"),
    74: ("FALSE", "Standard committee decision phrase (W12)"),
    75: ("FALSE", "7/15 days submission norm by price = 223-FZ ст.3.4 ч.5 (W4)"),
    76: ("FALSE", "verbatim 25% tax threshold (W4)"),
    77: ("FALSE", "Generic 'медная продукция' material"),
    78: ("FALSE", "Generic phrase about contract changes"),
    79: ("FALSE", "Production year 2025 for 2026 procurement = standard (1 year max)"),
    80: ("FALSE", "Absolute values requirement = standard for МСП аукцион (W11)"),
    81: ("FALSE", "ОКПД2 + work description — not narrow tech spec"),
    82: ("FALSE", "Meta reference to Спецификация (Приложение №1)"),
    83: ("FALSE", "Generic boilerplate 'качественным, соответствующим требованиям'"),
    84: ("FALSE", "Generic 'фильтры для компрессорного оборудования'"),
    85: ("FALSE", "Standard uklonenie procedure"),
    86: ("FALSE", "Standard rejection grounds (W12)"),
    87: ("FALSE", "Reference to Информационная карта + only price criterion = standard аукцион"),
    88: ("FALSE", "223-FZ ст.3.2 ч.21 (volume increase to НМЦК) — standard (W4)"),
    89: ("FALSE", "КТРУ catalog code — official catalog, not brand"),
    90: ("FALSE", "Generic 'стоимость Товара в полной комплектации'"),
    91: ("FALSE", "Specific facility address (Евпаторийский РЭС) — work location"),
    92: ("FALSE", "Заказчик's contact person (per codebook FALSE example)"),
    93: ("FALSE", "1/2 deadline rule = 223-FZ ст.3.2 ч.9 (W4)"),
    94: ("FALSE", "Generic 'Стоимость Товара в полной комплектации'"),
    95: ("FALSE", "3-year document retention = standard 223-FZ"),
    96: ("FALSE", "Generic theatre items (same as #17)"),
    97: ("FALSE", "Standard clarification deadline period"),
    98: ("FALSE", "Generic phrase 'не предоставил документы'"),
    99: ("FALSE", "Anti-corruption rule (no post-tender changes) = defensive (W13)"),
    100: ("PARTIAL", "30 раб.дн. for security return — borderline, slightly slower than typical 5-10"),
    101: ("TRUE", "REAL: «Порядок оценки и сопоставления заявок | Не предусмотрено» — empty eval"),
    102: ("FALSE", "1/2 deadline rule = 223-FZ ст.3.2 ч.9 (W4)"),
    103: ("FALSE", "10-20 days for contract = standard 223-FZ (W4)"),
    104: ("FALSE", "Standard right to cancel before deadline (W12)"),
    105: ("FALSE", "Fragment 'предложенных в заявке... с которым заключается договор'"),
    106: ("FALSE", "1/2 deadline rule = 223-FZ ст.3.2 ч.9 (W4)"),
    107: ("FALSE", "Meta reference to информационная карта"),
    108: ("FALSE", "verbatim 25% tax threshold (W4)"),
    109: ("FALSE", "Standard НДС/tax neutral pricing clause"),
    110: ("FALSE", "Standard uklonenie consequence (bid security forfeited)"),
    111: ("FALSE", "Auction has only price criterion — 223-FZ norm (W10)"),
    112: ("FALSE", "Specific work object (Санаторий Полтава-Крым) — заказчик's facility"),
    113: ("FALSE", "1/2 deadline rule = 223-FZ ст.3.2 ч.9 (W4)"),
    114: ("FALSE", "3 раб.дн. for clarifications = 223-FZ ст.3.2 ч.11 (W4)"),
    115: ("FALSE", "Generic fragment 'установке, настройке, вводу в эксплуатацию'"),
    116: ("FALSE", "3-day publication of changes = 223-FZ standard (W4)"),
    117: ("FALSE", "Just contract price 5.8m RUB — no requirement"),
    118: ("FALSE", "Auction has only price criterion (W10)"),
    119: ("FALSE", "verbatim 25% tax threshold (W4)"),
    120: ("FALSE", "ОКПД-2 work category — standard classification, not specialized"),
    121: ("FALSE", "Generic 'мебель (диваны)' category"),
    122: ("FALSE", "18-min auction duration is normal for electronic auction"),
    123: ("FALSE", "Standard rule: clarifications cannot change subject (W13)"),
    124: ("FALSE", "Generic 'качество должно соответствовать законодательству'"),
    125: ("FALSE", "3 раб.дн. for protocol of disagreements = 223-FZ ст.3.2 ч.15 (W4)"),
    126: ("FALSE", "10 months residual shelf life — standard medical"),
    127: ("FALSE", "Anti-double-meaning rule for bidders (W11)"),
    128: ("FALSE", "Just protocol entry 'решение не предоставлено'"),
}


def main() -> None:
    assert len(VERDICTS) == 128, f"Expected 128 verdicts, got {len(VERDICTS)}"

    out_lines = []
    for i, flag in enumerate(PACK, 1):
        verdict, reason = VERDICTS[i]
        rec = {
            "n": i,
            "flag_id": flag["flag_id"],
            "tender_id": flag["tender_id"],
            "label": flag["label"],
            "section": flag["section"],
            "lot_risk": flag["lot_risk"],
            "category": flag["_category"],
            "verdict": verdict,
            "reason": reason,
            "annotator": "claude_opus_4.7",
            "annotated_at": "2026-05-06",
        }
        out_lines.append(json.dumps(rec, ensure_ascii=False))

    OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    # Summary
    from collections import Counter
    by_v = Counter(v for v, _ in VERDICTS.values())
    by_lbl = Counter()
    by_cat = Counter()
    for i, flag in enumerate(PACK, 1):
        v, _ = VERDICTS[i]
        by_lbl[(flag["label"], v)] += 1
        by_cat[(flag["_category"], v)] += 1

    print(f"Wrote {len(out_lines)} annotations to {OUT}")
    print(f"\nBy verdict: {dict(by_v)}")
    print("\nBy label x verdict:")
    labels = sorted({l for l, _ in by_lbl})
    for lbl in labels:
        t = by_lbl.get((lbl, "TRUE"), 0)
        p = by_lbl.get((lbl, "PARTIAL"), 0)
        f = by_lbl.get((lbl, "FALSE"), 0)
        print(f"  {lbl}: T={t} P={p} F={f}")
    print("\nBy category x verdict:")
    cats = sorted({c for c, _ in by_cat})
    for cat in cats:
        t = by_cat.get((cat, "TRUE"), 0)
        p = by_cat.get((cat, "PARTIAL"), 0)
        f = by_cat.get((cat, "FALSE"), 0)
        print(f"  {cat}: T={t} P={p} F={f}")


if __name__ == "__main__":
    main()
