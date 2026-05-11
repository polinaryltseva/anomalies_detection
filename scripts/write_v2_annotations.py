"""Write verdicts for 74 flags from v2_review_pack."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/labeled/v2_flag_annotations.jsonl"
PACK = json.loads((ROOT / "data/labeled/v2_review_pack.json").read_text(encoding="utf-8"))


# Verdicts indexed by flag # (1-74) — based on systematic codebook v3 (W1-W15) review
VERDICTS: dict[int, tuple[str, str]] = {
    1: ("FALSE", "generic phrase 'поставляемого товара' — not brand"),
    2: ("FALSE", "Just describes process of publishing changes — not burden"),
    3: ("FALSE", "Generic category 'лакокрасочные материалы' — no brand"),
    4: ("FALSE", "Bank account confirmation = standard 223-FZ requirement (W9)"),
    5: ("FALSE", "20 days for contract = standard 223-FZ ст.3.2 ч.15 (W4)"),
    6: ("FALSE", "'Победителем признается участник, предложивший наиболее низкую цену' = OBVIOUS price criterion for аукцион (W10)"),
    7: ("FALSE", "verbatim 223-FZ ст.3 ч.10.1 25% threshold (W4)"),
    8: ("FALSE", "Standard contact person info — not COI signal"),
    9: ("FALSE", "verbatim 223-FZ regulatory text (W12)"),
    10: ("PARTIAL", "1-day modification window — borderline, ст.3.2 ч.9 minimum is half deadline"),
    11: ("TRUE", "REAL: «Критерии оценки заявок | Не применяется» — same pattern as ensemble TRUEs"),
    12: ("FALSE", "3 раб.дн. for protocol of disagreements = standard 223-FZ ст.3.2 ч.15 (W4)"),
    13: ("PARTIAL", "Качество участника как критерий — может быть subjective if not detailed"),
    14: ("FALSE", "verbatim 25% tax threshold (W4)"),
    15: ("FALSE", "Standard anti-corruption clause (W12)"),
    16: ("FALSE", "Just describes when SRO requirements apply — not actual requirement"),
    17: ("FALSE", "Generic phrase about TZ requirements — not specific spec"),
    18: ("FALSE", "Vague reference to documentation — not actual burden"),
    19: ("FALSE", "Same-day price submission = standard auction procedure"),
    20: ("FALSE", "Standard collective bidder agreement requirement"),
    21: ("FALSE", "3 раб.дн. for clarifications = standard ст.3.2 ч.11"),
    22: ("PARTIAL", "Payment 30.03.2027 vs submission 2026 — possibly extreme deferment, depends on contract type"),
    23: ("FALSE", "Generic phrase about parameter specification per item type"),
    24: ("FALSE", "verbatim 223-FZ ст.3.2 ч.6 (W12)"),
    25: ("FALSE", "OCR-encoded text, не разобрать"),
    26: ("TRUE", "REAL: «Порядок оценки и сопоставления заявок | Не предусмотрено»"),
    27: ("FALSE", "'Тормозная жидкость' — generic commodity, not brand"),
    28: ("FALSE", "Just bid ranking output — not evaluation criteria gap"),
    29: ("FALSE", "Empty contract date placeholder 'г. Калуга 2026 г.'"),
    30: ("FALSE", "Generic procedure description"),
    31: ("FALSE", "Notarized translation for foreign docs = standard requirement"),
    32: ("FALSE", "'Critria applied equally' = defensive rule (W13)"),
    33: ("FALSE", "СРО compensation fund — mandatory ст.55.4 Градкодекса"),
    34: ("PARTIAL", "90% remaining shelf life — strict but not unique to one supplier"),
    35: ("FALSE", "'Замена стеклопакетов' — generic service name"),
    36: ("FALSE", "verbatim 223-FZ ст.3.2 ч.10 large deal consent (W12)"),
    37: ("FALSE", "verbatim 223-FZ clarifications procedure"),
    38: ("FALSE", "'гидрантов пожарных' — generic commodity"),
    39: ("FALSE", "Generic obligation to accept and pay"),
    40: ("FALSE", "10-20 days = verbatim ст.3.2 ч.15 (W4)"),
    41: ("FALSE", "Abstract phrase, no specific spec mentioned"),
    42: ("FALSE", "Just NMTsK = starting price, not requirement"),
    43: ("FALSE", "Too generic 'signing contract'"),
    44: ("FALSE", "WRONG label: about deadlines, not brand"),
    45: ("PARTIAL", "Refers to internal Положение о закупке — could be vague but legitimate"),
    46: ("FALSE", "'поставка фланцев' = generic commodity"),
    47: ("FALSE", "'трубы полипропиленовые' = generic commodity"),
    48: ("FALSE", "Standard defensive clause about bidder costs"),
    49: ("FALSE", "Generic compliance statement"),
    50: ("FALSE", "Anti-collusion rule — defensive, not restrictive"),
    51: ("FALSE", "Standard right to cancel auction"),
    52: ("PARTIAL", "1-day modification window — borderline same as #10"),
    53: ("FALSE", "3 раб.дн. = standard"),
    54: ("FALSE", "Generic clause without specifics"),
    55: ("FALSE", "Just section title 'техническое задание'"),
    56: ("FALSE", "Customer name (kindergarten) is not COI signal"),
    57: ("FALSE", "Encoded OCR text, не разобрать"),
    58: ("FALSE", "Standard 'no third-party rights' clause"),
    59: ("FALSE", "«критерии не устанавливаются для аукциона» = correct per W10 (price-only)"),
    60: ("FALSE", "Generic phrase about government procurement"),
    61: ("FALSE", "Oil 10W-40 API SG/CD = technical standard (SAE/API), not brand"),
    62: ("TRUE", "REAL: «порядок оценки не предусмотрен»"),
    63: ("FALSE", "verbatim 25% tax threshold (W4)"),
    64: ("FALSE", "3 раб.дн. = standard"),
    65: ("FALSE", "7 days minimum = ст.3.2 ч.9 protective rule (W13)"),
    66: ("PARTIAL", "«Скоросшиватель Дело №» — 'Дело №' may be brand or just numbering"),
    67: ("FALSE", "'ведра черные мусорные' = generic descriptive"),
    68: ("FALSE", "СРО ответственность ≥ цена = ст.55.8 Градкодекса (mandatory)"),
    69: ("FALSE", "OCR encoded — just NMTsK"),
    70: ("FALSE", "Cancel only force majeure = protective rule (W13)"),
    71: ("FALSE", "Empty contract date placeholder"),
    72: ("FALSE", "1.5× НМЦК limit = ст.3.4 ч.5 protective ceiling (W13)"),
    73: ("PARTIAL", "1-hour price submission window — strict but typical for electronic auction"),
    74: ("FALSE", "Generic statement about deadline"),
}


def main():
    rows = []
    for i, flag in enumerate(PACK, 1):
        verdict, reason = VERDICTS[i]
        rows.append({
            "n": i,
            "flag_id": flag["flag_id"],
            "tender_id": flag["tender_id"],
            "label": flag["label"],
            "section": flag["section"],
            "lot_risk": flag["lot_risk"],
            "verdict": verdict,
            "reason": reason,
            "annotator": "claude_opus_4.7",
            "annotated_at": "2026-05-05",
        })

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    v = Counter(r["verdict"] for r in rows)
    print(f"Wrote {len(rows)} v2 annotations -> {OUT}")
    print(f"Verdicts: {dict(v)}")
    n = len(rows)
    print(f"Strict precision: {v.get('TRUE',0)/n:.1%}")
    print(f"Loose precision: {(v.get('TRUE',0)+v.get('PARTIAL',0))/n:.1%}")

    # Stats by label
    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], Counter())[r["verdict"]] += 1
    print("\nBy label:")
    for lbl, c in sorted(by_label.items()):
        n_ = sum(c.values())
        t = c.get("TRUE", 0)
        p = c.get("PARTIAL", 0)
        f_ = c.get("FALSE", 0)
        print(f"  {lbl}: T={t} P={p} F={f_} (n={n_})")


if __name__ == "__main__":
    main()
