"""Build v2 OpenAI fine-tuning dataset with balanced classes.

Sources:
- bulk_flag_annotations.jsonl (121 v1 manual)
- v2_flag_annotations.jsonl (74 v2 manual)
- ensemble_annotations.jsonl (7 ensemble manual)
- gpt55_annotations.jsonl (4 gpt-5.5 silver)
- rule_trues.jsonl (78 rule-based TRUE)

Strategy:
- All TRUE+PARTIAL → kept (positive class, ~110 examples)
- FALSE → downsampled to match TRUE count (~110 examples) for ~50/50 balance
- Augment 20+ negative-only examples from bottom-10 manually-clean lots
- Total target: 250-280 examples

Output: data/finetune_v2/training.jsonl + validation.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

random.seed(42)

OUT_DIR = ROOT / "data/finetune_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW = ROOT / "data/raw/bulk"

SYSTEM_PROMPT_SHORT = """Ты — эксперт по комплаенсу в коммерческих закупках 223-ФЗ.
Прочитай фрагмент тендерной документации и найди РЕАЛЬНЫЕ признаки ограничения
конкуренции. Игнорируй стандартные обязательные нормы 223-ФЗ (анти-COI клаузула,
СМП-only режим, Russian origin priority, стандартные сроки 5/4/25/7/10 дней,
бренд С «или эквивалент», описания структуры заявки, цитаты статей закона).

Флагать только: брендинг без эквивалента, экстремальные сроки оплаты ≥120 дн,
прямой бан слов «или эквивалент», пустые критерии оценки, конкретные ФИО
аффилированных лиц.

Возвращай JSON: {"flags": [{"label", "section", "span_text", "confidence",
"rationale", "regulatory_reference"}, ...]}. Если признаков нет — пустой массив.

Метки: brand_or_model_targeting, restrictive_tech_specs,
disproportionate_qualification, documentary_burden, ambiguous_evaluation_criteria,
unusual_short_deadlines, unusual_contract_terms, conflict_of_interest_signals.
"""


def gather_sections(lot_id: str) -> dict[str, str]:
    d = RAW / lot_id
    if not d.exists():
        return {}
    parts = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}:
            continue
        ed = extract(f)
        if ed.text:
            parts.append(f"\n\n=== {f.name} ===\n\n{ed.text}")
    full = "\n".join(parts)
    sections = merge_sections(segment(full))
    if not sections:
        sections = {"unsegmented": full}
    return sections


def load_all_annotations() -> list[dict]:
    """Combine all annotation sources into unified list of records."""
    all_anns = []

    # v1 bulk (121 with full pack info)
    bulk_pack = json.loads((ROOT / "data/labeled/bulk_review_pack.json").read_text(encoding="utf-8"))
    bulk_ann = [json.loads(l) for l in
                (ROOT / "data/labeled/bulk_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    pack_by_id = {f["flag_id"]: f for f in bulk_pack}
    for a in bulk_ann:
        f = pack_by_id.get(a["flag_id"])
        if not f:
            continue
        all_anns.append({
            "tender_id": a["tender_id"],
            "label": a["label"],
            "section": f.get("section", "unsegmented"),
            "span_text": f["span_text"],
            "rationale": f.get("rationale", ""),
            "regulatory_reference": f.get("regulatory_reference", ""),
            "confidence": f.get("confidence", 0.7),
            "verdict": a["verdict"],
            "source": "v1",
        })

    # v2 review (74 from held-out)
    v2_pack = json.loads((ROOT / "data/labeled/v2_review_pack.json").read_text(encoding="utf-8"))
    v2_ann = [json.loads(l) for l in
              (ROOT / "data/labeled/v2_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    v2_by_id = {f["flag_id"]: f for f in v2_pack}
    for a in v2_ann:
        f = v2_by_id.get(a["flag_id"])
        if not f:
            continue
        all_anns.append({
            "tender_id": a["tender_id"],
            "label": a["label"],
            "section": f.get("section", "unsegmented"),
            "span_text": f["span_text"],
            "rationale": f.get("rationale", ""),
            "regulatory_reference": f.get("regulatory_reference", ""),
            "confidence": f.get("confidence", 0.7),
            "verdict": a["verdict"],
            "source": "v2_review",
        })

    # Rule-based TRUE
    rule_ann = [json.loads(l) for l in
                (ROOT / "data/labeled/rule_trues.jsonl").read_text(encoding="utf-8").splitlines()]
    for a in rule_ann:
        all_anns.append({
            **a,
            "source": "rule",
        })

    # ensemble + gpt55 — augment v1 patterns
    ens_ann = [json.loads(l) for l in
               (ROOT / "data/labeled/ensemble_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    ens_dir = ROOT / "data/reports/bulk_ensemble"
    for a in ens_ann:
        report_path = ens_dir / f"{a['tender_id']}.json"
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for fl in report["flags"]:
            if fl["label"] == a["label"]:
                all_anns.append({
                    "tender_id": a["tender_id"],
                    "label": a["label"],
                    "section": fl["section"],
                    "span_text": fl["span_text"],
                    "rationale": fl.get("rationale", ""),
                    "regulatory_reference": fl.get("regulatory_reference", ""),
                    "confidence": fl.get("confidence", 0.7),
                    "verdict": a["verdict"],
                    "source": "ensemble",
                })
                break

    return all_anns


def build_examples(annotations: list[dict]) -> list[dict]:
    # Group by (tender_id, section) — examples are section-level
    by_lot_section = defaultdict(list)
    for a in annotations:
        by_lot_section[(a["tender_id"], a.get("section", "unsegmented"))].append(a)

    print(f"Unique (lot, section) groups: {len(by_lot_section)}")

    tender_ids = sorted({tid for tid, _ in by_lot_section})
    print(f"Unique tenders: {len(tender_ids)}")

    section_cache: dict[str, dict[str, str]] = {}
    for tid in tender_ids:
        section_cache[tid] = gather_sections(tid)

    pos_examples = []
    neg_examples = []

    for (tid, section), flags in by_lot_section.items():
        sections = section_cache.get(tid, {})
        section_text = sections.get(section, "")
        if not section_text:
            # Try unsegmented fallback
            section_text = sections.get("unsegmented", "")
            if not section_text:
                continue
        if len(section_text) < 50:
            continue

        section_text_trimmed = section_text[:4000]
        kept_flags = []
        for a in flags:
            if a["verdict"] in ("TRUE", "PARTIAL"):
                kept_flags.append({
                    "label": a["label"],
                    "section": section,
                    "span_text": a["span_text"][:500],
                    "confidence": 0.85 if a["verdict"] == "TRUE" else 0.55,
                    "rationale": (a.get("rationale") or "")[:200],
                    "regulatory_reference": (a.get("regulatory_reference") or "")[:200],
                })

        user_msg = (
            f"Tender ID: {tid}\n"
            f"Section: {section}\n\n"
            f"Текст секции:\n---\n{section_text_trimmed}\n---\n\n"
            f"Найди реальные признаки ограничения конкуренции."
        )
        assistant_msg = json.dumps({"flags": kept_flags}, ensure_ascii=False)

        ex = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_SHORT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            "_n_kept": len(kept_flags),
            "_tid": tid,
        }
        if kept_flags:
            pos_examples.append(ex)
        else:
            neg_examples.append(ex)

    print(f"Positive (>=1 flag): {len(pos_examples)}")
    print(f"Negative (empty flags): {len(neg_examples)}")

    # Add bottom-10 negative-only examples
    bottom_10 = ['169629544', '169596415', '169608004', '169633366', '169618156',
                 '169608015', '169633302', '169618157', '169625477', '169629441']
    annotated_sections = set(by_lot_section.keys())
    extra_neg_count = 0
    for tid in bottom_10:
        if tid not in section_cache:
            section_cache[tid] = gather_sections(tid)
        sections = section_cache[tid]
        for sname, stext in sections.items():
            if (tid, sname) in annotated_sections:
                continue
            if not stext or len(stext) < 200:
                continue
            stext_trimmed = stext[:4000]
            user_msg = (
                f"Tender ID: {tid}\n"
                f"Section: {sname}\n\n"
                f"Текст секции:\n---\n{stext_trimmed}\n---\n\n"
                f"Найди реальные признаки ограничения конкуренции."
            )
            assistant_msg = json.dumps({"flags": []}, ensure_ascii=False)
            neg_examples.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_SHORT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ],
                "_n_kept": 0,
                "_tid": tid,
            })
            extra_neg_count += 1
    print(f"Added {extra_neg_count} negative examples from bottom-10")

    # Balance: downsample negatives to match positives + 20% buffer
    target_neg = int(len(pos_examples) * 1.2)
    if len(neg_examples) > target_neg:
        random.shuffle(neg_examples)
        neg_examples = neg_examples[:target_neg]
        print(f"Downsampled negatives to {target_neg}")

    examples = pos_examples + neg_examples
    print(f"Final: {len(examples)} examples ({len(pos_examples)} pos / {len(neg_examples)} neg)")
    return examples


def main() -> None:
    anns = load_all_annotations()
    print(f"Loaded {len(anns)} total annotations")
    print(f"By verdict: {Counter(a.get('verdict','?') for a in anns)}")
    print(f"By source: {Counter(a.get('source','?') for a in anns)}")

    examples = build_examples(anns)
    random.shuffle(examples)
    n_val = max(15, len(examples) // 10)
    val = examples[:n_val]
    train = examples[n_val:]

    def strip_meta(ex):
        return {"messages": ex["messages"]}

    train_path = OUT_DIR / "training.jsonl"
    val_path = OUT_DIR / "validation.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps(strip_meta(ex), ensure_ascii=False) + "\n")
    with val_path.open("w", encoding="utf-8") as f:
        for ex in val:
            f.write(json.dumps(strip_meta(ex), ensure_ascii=False) + "\n")

    total_chars = 0
    for ex in train:
        for m in ex["messages"]:
            total_chars += len(m["content"])
    est_tokens = total_chars // 4

    print(f"\nTrain: {len(train)} -> {train_path} ({train_path.stat().st_size//1024} KB)")
    print(f"Val:   {len(val)} -> {val_path}")
    print(f"\nEstimated tokens: ~{est_tokens:,}")
    print(f"Cost gpt-4.1: ~${est_tokens * 25 / 1_000_000:.2f}")


if __name__ == "__main__":
    main()
