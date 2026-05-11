"""Write verdicts for all 121 flags in bulk_review_pack.

Rules used (consistent with prior 123-flag annotation):
- TRUE: real anomaly per codebook label
- FALSE: false positive — model triggered on standard/legal 223-FZ language
- PARTIAL: real anomaly but borderline (e.g., legal compatibility exception under 223-FZ ст.3 ч.6.1)
  or correct under codebook but defensible as common practice (e.g., federal-list textbooks)

Annotator: Claude (light-touch single-pass review, 2026-05-04)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Verdicts indexed by flag #1-#121 from bulk_review_pack.json (sequential order in file)
# Format: (verdict, short_reason)
VERDICTS: dict[int, tuple[str, str]] = {
    # ──── bottom_10 (#1-12) — all FALSE ────
    1: ("FALSE", "standard 223-FZ language: 'заявка содержит сведения и документы'"),
    2: ("FALSE", "1 year experience for AC install — minimal, not disproportionate"),
    3: ("FALSE", "SMSP-only auction is legal per 223-FZ ст.3 ч.4"),
    4: ("FALSE", "25% tax debt threshold is verbatim 223-FZ language"),
    5: ("FALSE", "single-bidder contract is procedural fact, not COI signal"),
    6: ("FALSE", "single-bidder contract — same procedural pattern as #5"),
    7: ("FALSE", "SMSP-only auction is legal"),
    8: ("FALSE", "single-bidder contract — procedural"),
    9: ("FALSE", "contact person is mandatory by law, not COI"),
    10: ("FALSE", "'по согласованной сторонами стоимости' is standard contract phrase"),
    11: ("FALSE", "section header 'Требования к Заявке', not actual requirement"),
    12: ("FALSE", "Russian origin priority is standard 223-ФЗ ПП РФ № 1875"),

    # ──── brand_targeting_all (#13-84) ────
    13: ("FALSE", "meta legal text describing required заявка contents"),
    14: ("FALSE", "meta legal text — list of attributes заявка may contain"),
    15: ("FALSE", "quoting 223-FZ rule that trademarks must have 'или эквивалент'"),
    16: ("TRUE", "REAL: rule forbidding bidder from using 'эквивалент' next to trademark name"),
    17: ("FALSE", "MIRKA Abralon brand WITH 'или эквивалент' — legal under 223-FZ"),
    18: ("FALSE", "MIRKA Abralon brand WITH 'или эквивалент'"),
    19: ("FALSE", "MIRKA Abralon brand WITH 'или эквивалент'"),
    20: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    21: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    22: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    23: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    24: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    25: ("FALSE", "ABRANET MIRKA brand WITH 'или эквивалент'"),
    26: ("FALSE", "MIRKA brand WITH 'или эквивалент'"),
    27: ("FALSE", "meta legal text 'указание на товарный знак (при наличии)'"),
    28: ("FALSE", "Certa brand WITH 'или эквивалент'"),
    29: ("FALSE", "Veiro Professional WITH 'или эквивалент'"),
    30: ("FALSE", "Stayer WITH 'или эквивалент'"),
    31: ("FALSE", "Dali WITH 'или эквивалент'"),
    32: ("FALSE", "meta legal text"),
    33: ("FALSE", "meta legal text 'согласие на использование товара...'"),
    34: ("FALSE", "meta legal text 'указание на товарный знак и (или) конкретных показателях'"),
    35: ("FALSE", "POSITIVE statement: all trademarks accompanied by 'или эквивалент'"),
    36: ("FALSE", "Russian origin priority — standard 223-FZ"),
    37: ("TRUE", "REAL: rule explicitly forbidding use of 'или эквивалент' in TZ"),
    38: ("PARTIAL", "Боголюбов textbook — federal-list, but specific author named without alternatives"),
    39: ("PARTIAL", "Боголюбов textbook — same"),
    40: ("PARTIAL", "Мединский textbook — federal-list, specific author"),
    41: ("PARTIAL", "Мединский textbook — same"),
    42: ("FALSE", "Russian origin priority — meta description of preference rules"),
    43: ("FALSE", "wrong category: rule about NOT identifying bidder in part 1, not brand targeting"),
    44: ("FALSE", "meta conditional 'if there are trademark mentions...'"),
    45: ("FALSE", "generic precision requirement, not brand-related"),
    46: ("FALSE", "quoting 223-FZ requirement to use 'или эквивалент'"),
    47: ("TRUE", "REAL: requires bidder to specify exact name/article + bans 'эквивалент'"),
    48: ("FALSE", "meta legal text about required заявка info"),
    49: ("PARTIAL", "compatibility exception 223-FZ ст.3 ч.6.1 п.3 — defensible but brand named"),
    50: ("FALSE", "meta legal text"),
    51: ("TRUE", "Технониколь ТЕХНОПЛЕКС specific model in contract without 'или эквивалент'"),
    52: ("FALSE", "meta legal text + 'должны сопровождаться или эквивалент' is positive"),
    53: ("FALSE", "ПАЗ 32053 — INSURANCE for existing fleet, can't substitute owned vehicle"),
    54: ("FALSE", "RENAULT LOGAN — insurance for existing vehicle"),
    55: ("FALSE", "LADA 2131 — insurance for existing vehicle"),
    56: ("FALSE", "ГАЗ 3009 D3 — insurance for existing vehicle"),
    57: ("FALSE", "УАЗ 390995 — insurance for existing vehicle"),
    58: ("FALSE", "МТЗ 80 — insurance for existing tractor"),
    59: ("FALSE", "КАМАЗ 55111 — insurance for existing vehicle"),
    60: ("FALSE", "ГАЗ 53 — insurance for existing vehicle"),
    61: ("FALSE", "ЭО 2626 — insurance for existing equipment"),
    62: ("FALSE", "quoting 223-FZ rule against trademark requirements"),
    63: ("FALSE", "meta legal text 'указание на товарный знак (при наличии)'"),
    64: ("TRUE", "OHAUS Adventurer Pro brand+model in pricing, no 'или эквивалент'"),
    65: ("FALSE", "meta legal text"),
    66: ("PARTIAL", "Cell Saver Elite — compatibility justification (223-FZ ст.3 ч.6.1)"),
    67: ("PARTIAL", "Haemonetics CellSaver Elite — compatibility for existing equipment"),
    68: ("FALSE", "meta legal text"),
    69: ("FALSE", "meta legal text 'согласие на использование товара...'"),
    70: ("FALSE", "'нержавеющая сталь' is generic material, not brand"),
    71: ("FALSE", "Russian origin priority — standard 223-FZ ПП 1875"),
    72: ("PARTIAL", "UserGate NGFW D500 — compatibility/upgrade for existing equipment"),
    73: ("TRUE", "Directum RX specific software system named without 'или эквивалент'"),
    74: ("FALSE", "Russian origin priority"),
    75: ("TRUE", "Dallas Lock specific brand for support certificates"),
    76: ("FALSE", "DTLH-15BG WITH 'или эквивалент' immediately following in title"),
    77: ("FALSE", "meta legal text demanding bidder specify brand"),
    78: ("FALSE", "meta legal text"),
    79: ("FALSE", "legal text describing case 'if no или эквивалент'"),
    80: ("FALSE", "same legal text as #79"),
    81: ("FALSE", "wrong label: SMSP-only restriction, not brand targeting"),
    82: ("FALSE", "Russian origin priority"),
    83: ("TRUE", "REAL: explicit ban on bidder using 'или эквивалент'"),
    84: ("FALSE", "meta legal text"),

    # ──── coi_sample_30 (#85-112) — all FALSE ────
    # Pattern: model triggers on STANDARD 223-FZ ст.3.1 anti-conflict-of-interest CHECK clause,
    # which is the requirement to verify NO conflict — not a signal that conflict exists.
    85: ("FALSE", "standard 223-FZ COI check clause"),
    86: ("FALSE", "standard COI check clause"),
    87: ("FALSE", "standard COI check clause"),
    88: ("FALSE", "standard COI check clause"),
    89: ("FALSE", "standard COI check clause"),
    90: ("FALSE", "standard COI check clause"),
    91: ("FALSE", "standard 223-FZ ст.3.1 official-bidder-identity check"),
    92: ("FALSE", "standard COI check clause"),
    93: ("FALSE", "standard anti-bribery clause"),
    94: ("FALSE", "FAS antitrust complaint suspension — standard"),
    95: ("FALSE", "naming organizer (DeloPorts container terminal) is not COI"),
    96: ("FALSE", "contact person — mandatory contact info"),
    97: ("FALSE", "standard COI check clause"),
    98: ("FALSE", "standard COI check clause"),
    99: ("FALSE", "anti-collusion rule (one bidder = one заявка)"),
    100: ("FALSE", "naming buyer (ГУП Мосводосток) is not COI"),
    101: ("FALSE", "wrong label: SMSP-only, not COI"),
    102: ("FALSE", "contact person — mandatory"),
    103: ("FALSE", "standard COI check clause"),
    104: ("FALSE", "standard COI check clause"),
    105: ("FALSE", "wrong label: SMSP-only"),
    106: ("FALSE", "standard COI check clause"),
    107: ("FALSE", "wrong label: Russian origin priority, not COI"),
    108: ("FALSE", "standard COI check clause"),
    109: ("FALSE", "standard COI check clause"),
    110: ("FALSE", "standard COI check clause"),
    111: ("FALSE", "wrong label: SMSP-only"),
    112: ("FALSE", "standard COI check clause"),

    # ──── top_3_sample (#113-121) — all FALSE ────
    113: ("FALSE", "'товар новый, год выпуска не ранее 2025' — standard new-item req"),
    114: ("FALSE", "section header — actual criterion is price (аукцион)"),
    115: ("FALSE", "SMSP-only — legal under 223-FZ"),
    116: ("FALSE", "standard required documents per 223-FZ"),
    117: ("FALSE", "SMSP-only — legal"),
    118: ("FALSE", "'не менее 150А' is minimum spec, not narrow brand-targeting"),
    119: ("FALSE", "standard COI check clause"),
    120: ("FALSE", "modular PLC is generic class requirement, not brand"),
    121: ("FALSE", "5-day signing window is standard 223-FZ deadline"),
}


def main() -> None:
    flags = json.loads((ROOT / "data/labeled/bulk_review_pack.json").read_text(encoding="utf-8"))
    assert len(flags) == 121, f"Expected 121, got {len(flags)}"

    out_path = ROOT / "data/labeled/bulk_flag_annotations.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for i, flag in enumerate(flags, 1):
            verdict, reason = VERDICTS[i]
            rec = {
                "n": i,
                "flag_id": flag["flag_id"],
                "tender_id": flag["tender_id"],
                "label": flag["label"],
                "sample_group": flag["sample_group"],
                "lot_risk_score": flag["lot_risk_score"],
                "verdict": verdict,
                "reason": reason,
                "annotator": "claude_opus_4.7",
                "annotated_at": "2026-05-04",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {out_path}")

    # Stats
    from collections import Counter, defaultdict
    by_group_verdict: dict[str, Counter] = defaultdict(Counter)
    by_label_verdict: dict[str, Counter] = defaultdict(Counter)
    overall = Counter()

    for i, flag in enumerate(flags, 1):
        v = VERDICTS[i][0]
        by_group_verdict[flag["sample_group"]][v] += 1
        by_label_verdict[flag["label"]][v] += 1
        overall[v] += 1

    print("\n=== OVERALL ===")
    total = sum(overall.values())
    for v in ["TRUE", "PARTIAL", "FALSE"]:
        n = overall.get(v, 0)
        print(f"  {v}: {n} ({100*n/total:.1f}%)")
    print(f"  Total: {total}")

    print("\n=== BY GROUP ===")
    for g in ["bottom_10", "brand_targeting_all", "coi_sample_30", "top_3_sample"]:
        c = by_group_verdict[g]
        n = sum(c.values())
        t = c.get("TRUE", 0)
        p = c.get("PARTIAL", 0)
        f_ = c.get("FALSE", 0)
        prec_strict = 100 * t / n if n else 0
        prec_loose = 100 * (t + p) / n if n else 0
        print(f"  {g}: TRUE={t} PARTIAL={p} FALSE={f_}  "
              f"(strict precision {prec_strict:.1f}%, loose {prec_loose:.1f}%)")

    print("\n=== BY LABEL ===")
    for label in sorted(by_label_verdict.keys()):
        c = by_label_verdict[label]
        n = sum(c.values())
        t = c.get("TRUE", 0)
        p = c.get("PARTIAL", 0)
        f_ = c.get("FALSE", 0)
        prec_strict = 100 * t / n if n else 0
        prec_loose = 100 * (t + p) / n if n else 0
        print(f"  {label}: TRUE={t} PARTIAL={p} FALSE={f_}  "
              f"(strict {prec_strict:.1f}%, loose {prec_loose:.1f}%)")


if __name__ == "__main__":
    main()
