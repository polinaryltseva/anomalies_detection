"""Build OpenAI fine-tuning dataset from our manual annotations.

Sources:
- data/labeled/bulk_flag_annotations.jsonl (121 verdicts)
- data/labeled/ensemble_annotations.jsonl (7 verdicts)
- data/labeled/gpt55_annotations.jsonl (4 verdicts)

For each (tender_id, section) tuple:
1. Get section text from raw documents (re-parse)
2. Filter manually-annotated flags to TRUE+PARTIAL
3. Build training example: (system_prompt, section_text) -> JSON with flags
4. For sections with no TRUE/PARTIAL -> empty flags array (negative example)

Plus add bottom-10 manually-verified-clean lots as full negative examples.

Output: data/finetune/training.jsonl + validation.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

random.seed(42)

OUT_DIR = ROOT / "data/finetune"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW = ROOT / "data/raw/bulk"

# Short system prompt for fine-tuning — модель выучит правила из примеров
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
    """Re-parse lot documents to get section texts."""
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


def load_annotations() -> list[dict]:
    """Combine all manual annotation sources."""
    all_anns = []

    # Source 1: bulk_review_pack annotations (121 with full bulk_review_pack info)
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
            "source": "bulk_pack",
        })

    # Source 2: ensemble annotations (7) — use existing reports for span info
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
    """Group annotations by (tender_id, section) and build training examples."""

    # Group flags by (tender_id, section)
    by_lot_section = defaultdict(list)
    for a in annotations:
        by_lot_section[(a["tender_id"], a["section"])].append(a)

    print(f"Unique (tender_id, section) groups: {len(by_lot_section)}")

    # Get unique tender_ids
    tender_ids = sorted({tid for tid, _ in by_lot_section})
    print(f"Unique tender_ids: {len(tender_ids)}")

    # Re-parse sections for each tender
    section_cache: dict[str, dict[str, str]] = {}
    for tid in tender_ids:
        section_cache[tid] = gather_sections(tid)
        if not section_cache[tid]:
            print(f"  WARN: no sections for {tid}")

    # Build positive examples: section with TRUE/PARTIAL flags
    examples = []
    skipped_empty = 0

    for (tid, section), flags in by_lot_section.items():
        sections = section_cache.get(tid, {})
        section_text = sections.get(section, "")
        if not section_text or len(section_text) < 50:
            skipped_empty += 1
            continue

        # Truncate to ~4K chars to fit context
        section_text_trimmed = section_text[:4000]

        # Build expected output: only TRUE+PARTIAL flags
        kept_flags = []
        for a in flags:
            if a["verdict"] in ("TRUE", "PARTIAL"):
                kept_flags.append({
                    "label": a["label"],
                    "section": section,
                    "span_text": a["span_text"][:500],
                    "confidence": 0.85 if a["verdict"] == "TRUE" else 0.55,
                    "rationale": a["rationale"][:200] if a["rationale"] else "",
                    "regulatory_reference": a["regulatory_reference"][:200] if a["regulatory_reference"] else "",
                })

        # Skip if section has FALSE flags but we already include this lot through TRUE flags elsewhere
        # Otherwise: section with all-FALSE flags = negative example (return empty)

        user_msg = (
            f"Tender ID: {tid}\n"
            f"Section: {section}\n\n"
            f"Текст секции:\n---\n{section_text_trimmed}\n---\n\n"
            f"Найди реальные признаки ограничения конкуренции."
        )
        assistant_msg = json.dumps({"flags": kept_flags}, ensure_ascii=False)

        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_SHORT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ],
            "_meta": {
                "tender_id": tid,
                "section": section,
                "n_true_partial": len(kept_flags),
                "n_total_flags": len(flags),
            },
        })

    print(f"Built {len(examples)} examples (skipped {skipped_empty} empty sections)")

    # Add purely-negative examples from bottom-10 lots (manually verified all-FALSE)
    # Pick sections from these lots that DON'T have any annotations
    bottom_10 = ['169629544', '169596415', '169608004', '169633366', '169618156',
                 '169608015', '169633302', '169618157', '169625477', '169629441']
    pos_examples_count = len(examples)
    annotated_sections = set(by_lot_section.keys())

    for tid in bottom_10:
        if tid not in section_cache:
            section_cache[tid] = gather_sections(tid)
        sections = section_cache[tid]
        for section_name, section_text in sections.items():
            if (tid, section_name) in annotated_sections:
                continue  # already covered
            if not section_text or len(section_text) < 200:
                continue
            section_text_trimmed = section_text[:4000]
            user_msg = (
                f"Tender ID: {tid}\n"
                f"Section: {section_name}\n\n"
                f"Текст секции:\n---\n{section_text_trimmed}\n---\n\n"
                f"Найди реальные признаки ограничения конкуренции."
            )
            assistant_msg = json.dumps({"flags": []}, ensure_ascii=False)
            examples.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_SHORT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ],
                "_meta": {
                    "tender_id": tid,
                    "section": section_name,
                    "n_true_partial": 0,
                    "n_total_flags": 0,
                    "neg_class": True,
                },
            })

    print(f"Added {len(examples) - pos_examples_count} negative examples from bottom-10 lots")
    print(f"Total: {len(examples)} examples")

    return examples


def main() -> None:
    annotations = load_annotations()
    print(f"Loaded {len(annotations)} annotations")

    from collections import Counter
    by_verdict = Counter(a["verdict"] for a in annotations)
    print(f"By verdict: {dict(by_verdict)}")

    examples = build_examples(annotations)

    # Shuffle & split 90/10 train/val
    random.shuffle(examples)
    n_val = max(10, len(examples) // 10)
    train = examples[n_val:]
    val = examples[:n_val]

    # Strip _meta before writing (OpenAI doesnt accept extra fields)
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

    # Token estimate
    total_chars = 0
    for ex in train:
        for m in ex["messages"]:
            total_chars += len(m["content"])
    est_tokens = total_chars // 4

    print(f"\nTrain: {len(train)} examples -> {train_path} ({train_path.stat().st_size//1024} KB)")
    print(f"Val:   {len(val)} examples -> {val_path}")
    print(f"\nEstimated train tokens: ~{est_tokens:,}")
    print(f"Fine-tune cost (gpt-4.1 @ $25/1M): ~${est_tokens * 25 / 1_000_000:.2f}")
    print(f"Fine-tune cost (gpt-4.1-mini @ $3/1M): ~${est_tokens * 3 / 1_000_000:.2f}")


if __name__ == "__main__":
    main()
