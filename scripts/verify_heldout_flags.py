"""Manual verdicts for all 74 flags from FT v2/v3a/v3a-mini on 20 heldout lots.

Verdicts based on codebook v3 (L1-L8 + W1-W15 whitelist) + 223-ФЗ knowledge.

Key rules applied:
- W10: для аукциона критерий = только цена → "критерии оценки не предусмотрены"
  with explicit "аукцион" context = FALSE
- W11: «эквивалент, аналог, должен быть» в инструкции участникам = FALSE
- W12: verbatim ссылки на 223-ФЗ статьи (например ч.19.4 ст.3.4) = FALSE
- Brand в TZ без «или эквивалент» = TRUE
- Brand только в price calc (preamble/pricing раздел НМЦК) = PARTIAL (suspicious но
  не legally enforced если в TZ generic описание)
- «Производитель, страна, торговая марка» = FALSE (table headers)
- Specific tech requirement (Qummy oven, УМ-35) = TRUE если без эквивалента
- ФИО заказчика в подписи / контакт = FALSE per codebook
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/eval/heldout_flags_with_context.json"
OUT_JSONL = ROOT / "data/labeled/heldout_flag_verdicts.jsonl"
OUT_MD = ROOT / "data/eval/heldout_verdicts_summary.md"


# Verdicts indexed by (tender_id, label, first_60_chars_of_span)
# Format: (tender_id, label, span_signature) -> (verdict, reason)
# verdict: TRUE / FALSE / PARTIAL
VERDICTS: dict[tuple[str, str, str], tuple[str, str]] = {

    # === Lot 169562196 (auction) ===
    ("169562196", "brand_or_model_targeting", "«эквивалент», «аналог»"): (
        "FALSE", "W11: bidder instruction — слова не должны сопровождаться «эквивалент», «аналог»"),
    ("169562196", "ambiguous_evaluation_criteria", "порядок оценки заявок"): (
        "FALSE", "W12+W10: verbatim ссылка на 223-ФЗ ст.3.4 ч.19.4 для аукциона = price-only"),
    ("169562196", "ambiguous_evaluation_criteria", "порядок оценки не предусмотрены"): (
        "FALSE", "W12+W10: same lot, частичный span — ссылка на 223-ФЗ для аукциона"),

    # === Lot 169596403 (auction) ===
    ("169596403", "ambiguous_evaluation_criteria", "Порядок оценки заявок и определ"): (
        "FALSE", "W10: «Победителем... предложивший наиболее низкую цену» = standard auction"),

    # === Lot 169562149 (auction) ===
    ("169562149", "brand_or_model_targeting", "«эквивалент», «аналог»"): (
        "FALSE", "W11: same bidder instruction pattern (NO_CONTEXT but signature matches)"),
    ("169562149", "ambiguous_evaluation_criteria", "Этап оценки и сопоставления не"): (
        "FALSE", "W10: «при проведении аукциона цена (100%)» = standard auction"),
    ("169562149", "ambiguous_evaluation_criteria", "Критерии оценки и сопоставлени"): (
        "FALSE", "W10: same — auction price-only"),

    # === Lot 169424481 (electric infra construction) ===
    ("169424481", "brand_or_model_targeting", "«эквивалент», «аналог»"): (
        "FALSE", "W11: bidder instruction in п.3.1.11 — слова не должны сопровождаться"),
    ("169424481", "brand_or_model_targeting", "3.1.11. Предоставляемые участни"): (
        "FALSE", "W11: same п.3.1.11 — bidder instruction"),
    ("169424481", "brand_or_model_targeting", "Предоставляемые участником закуп"): (
        "FALSE", "W11: same — mini caught it correctly per noisy regex"),

    # === Lot 169568308 (auction) ===
    ("169568308", "ambiguous_evaluation_criteria", "критерии оценки и сопоставлен"): (
        "FALSE", "W10: «электронном аукционе не устанавливаются» — standard auction"),

    # === Lot 169568334 ===
    ("169568334", "brand_or_model_targeting", "«эквивалент», «аналог»"): (
        "FALSE", "W11: bidder instruction (NO_CONTEXT but signature matches W11 pattern)"),

    # === Lot 169548175 ===
    ("169548175", "ambiguous_evaluation_criteria", "оценка заявок, окончательных"): (
        "FALSE", "Procedural: protocol formatting requirements, not actual evaluation criteria gap"),

    # === Lot 146961063 (kitchen equipment with Qummy oven) ===
    ("146961063", "brand_or_model_targeting", "QR-код с алгоритмом распознав"): (
        "TRUE", "Specific brand requirement: «роботизированная печь Qummy» без «или эквивалент»"),
    ("146961063", "restrictive_tech_specs", "QR-код с алгоритмом распознав"): (
        "TRUE", "Specific brand-locked tech req: QR-код для конкретной модели Qummy"),

    # === Lot 148493841 (antifreeze fleet maintenance) ===
    # All 14 LUXE/AGA/Oil Right brand flags are in section=preamble (НМЦК price calc table)
    # These are commercial price benchmarks, not strict TZ requirements
    # Marking PARTIAL: brands explicitly listed but legally non-binding if TZ uses generic specs
    ("148493841", "brand_or_model_targeting", "Антифриз LUXE ANTIFREEZE LONG L"): (
        "PARTIAL", "Brand LUXE in price calc (preamble НМЦК table), не в TZ"),
    ("148493841", "brand_or_model_targeting", "Антифриз LUXE ANTIFREEZE LONG"): (
        "PARTIAL", "Brand LUXE — same pattern (mini truncation)"),
    ("148493841", "brand_or_model_targeting", "Антифриз, готовый к применени"): (
        "PARTIAL", "Brand AGA ANTIFREEZE in НМЦК price calc"),
    ("148493841", "brand_or_model_targeting", "Антифриз зеленый Oil Right"): (
        "PARTIAL", "Brand Oil Right in НМЦК price calc"),
    ("148493841", "brand_or_model_targeting", "Антифриз красный Oil Right"): (
        "PARTIAL", "Brand Oil Right in НМЦК price calc"),

    # === Lot 149476638 (cafeteria food procurement) ===
    # Same pattern: brands in pricing section НМЦК, not strict TZ
    ("149476638", "brand_or_model_targeting", "Снэки кукур.\"СырBall\""): (
        "PARTIAL", "Brand «СырBall» in pricing НМЦК"),
    ("149476638", "brand_or_model_targeting", "Снэки хруст.\"Краб Рома\""): (
        "PARTIAL", "Brand «Краб Рома» in pricing"),
    ("149476638", "brand_or_model_targeting", "Сухарики \"Хрустим\""): (
        "PARTIAL", "Brand «Хрустим» in pricing"),
    ("149476638", "brand_or_model_targeting", "Чипсы\"Lays \""): (
        "PARTIAL", "Brand Lays in pricing"),
    ("149476638", "brand_or_model_targeting", "Чипсы\"Читос\""): (
        "PARTIAL", "Brand «Читос» in pricing"),
    ("149476638", "brand_or_model_targeting", "Печенье \" ОРЕО\""): (
        "PARTIAL", "Brand OREO in pricing"),
    ("149476638", "brand_or_model_targeting", "Батончик \" 35 \""): (
        "PARTIAL", "Brand «35» (M&M's variant?) — generic in pricing"),
    ("149476638", "brand_or_model_targeting", "Батончик \"Алёнка\""): (
        "PARTIAL", "Brand Алёнка in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад в \"Аленка\""): (
        "PARTIAL", "Brand Алёнка in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Аленка\""): (
        "PARTIAL", "Brand Алёнка in pricing"),
    ("149476638", "brand_or_model_targeting", "Леденцы \"Холс\""): (
        "PARTIAL", "Brand Halls in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Picnic\""): (
        "PARTIAL", "Brand Picnic in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"Баунти\""): (
        "PARTIAL", "Brand Bounty in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"М@М\""): (
        "PARTIAL", "Brand M&M's in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"Марс\""): (
        "PARTIAL", "Brand Mars in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"Милки Вэй\""): (
        "PARTIAL", "Brand Milky Way in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"Сникерс\""): (
        "PARTIAL", "Brand Snickers in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад\"Твикс\""): (
        "PARTIAL", "Brand Twix in pricing"),
    ("149476638", "brand_or_model_targeting", "\"РОНДО\" мята"): (
        "PARTIAL", "Brand «РОНДО» in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Кит-Кат\""): (
        "PARTIAL", "Brand Kit-Kat in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Кит-Кат\" киндер"): (
        "PARTIAL", "Brand Kit-Kat in pricing"),
    ("149476638", "brand_or_model_targeting", "Конфеты \"Аленка\""): (
        "PARTIAL", "Brand Алёнка in pricing"),
    ("149476638", "brand_or_model_targeting", "Конфеты \"Аленка\" молочные"): (
        "PARTIAL", "Brand Алёнка in pricing"),
    ("149476638", "brand_or_model_targeting", "Конфеты \"Карамель-микс\""): (
        "PARTIAL", "Brand «Карамель-микс» in pricing"),
    ("149476638", "brand_or_model_targeting", "Конфеты желейн. \"FRUTELLA\""): (
        "PARTIAL", "Brand FRUTELLA in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Несквик\" 28г"): (
        "PARTIAL", "Brand Несквик (Nesquik) in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Несквик\" батончик"): (
        "PARTIAL", "Brand Несквик in pricing"),
    ("149476638", "brand_or_model_targeting", "Шоколад \"Нестле-Натс\""): (
        "PARTIAL", "Brand Нестле-Натс / МегаБайт in pricing"),
    ("149476638", "brand_or_model_targeting", "Конфета жеват. \"FRUTELLA\""): (
        "PARTIAL", "Brand FRUTELLA in pricing"),
}


def span_signature(span: str, n: int = 30) -> str:
    """Normalize for matching — first N chars of stripped span."""
    return span.strip()[:n]


def main() -> None:
    flags = json.loads(SRC.read_text(encoding="utf-8"))
    print(f"Loaded {len(flags)} flag instances")

    # Match each flag to a verdict by (tender_id, label, signature)
    annotated = []
    unmatched = []
    for flag in flags:
        tid = flag["tender_id"]
        lbl = flag["label"]
        sig = span_signature(flag["span_text"])
        # Try to find verdict by signature prefix-matching
        verdict = None
        reason = None
        for (vtid, vlbl, vsig), (v, r) in VERDICTS.items():
            if vtid == tid and vlbl == lbl and (sig.startswith(vsig[:30]) or vsig.startswith(sig[:30])):
                verdict, reason = v, r
                break
        if verdict is None:
            unmatched.append(flag)
            verdict, reason = "UNREVIEWED", "no verdict mapping"
        annotated.append({**flag, "verdict": verdict, "reason": reason})

    # Stats per model
    by_model_verdict = defaultdict(Counter)
    for a in annotated:
        by_model_verdict[a["model"]][a["verdict"]] += 1

    print("\n=== Verdicts per model ===")
    for m in ("FT_v2", "FT_v3a", "FT_v3a_mini"):
        c = by_model_verdict[m]
        total = sum(c.values())
        true_n = c.get("TRUE", 0)
        partial_n = c.get("PARTIAL", 0)
        false_n = c.get("FALSE", 0)
        unrev = c.get("UNREVIEWED", 0)
        strict_p = (true_n / total * 100) if total else 0
        loose_p = ((true_n + partial_n) / total * 100) if total else 0
        print(f"\n{m}: {total} flags")
        print(f"  TRUE     : {true_n}")
        print(f"  PARTIAL  : {partial_n}")
        print(f"  FALSE    : {false_n}")
        print(f"  UNREVIEWED: {unrev}")
        print(f"  Strict precision (TRUE only)      : {strict_p:.1f}%")
        print(f"  Loose precision (TRUE+PARTIAL)    : {loose_p:.1f}%")

    if unmatched:
        print(f"\n=== UNMATCHED ({len(unmatched)}): ===")
        for u in unmatched:
            sig = span_signature(u["span_text"], 60)
            print(f"  [{u['tender_id']}/{u['model']}] {u['label']}: {sig!r}")

    # Save annotations
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for a in annotated:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"\nSaved -> {OUT_JSONL}")


if __name__ == "__main__":
    main()
