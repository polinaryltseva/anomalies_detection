"""Run inference with FT model on heldout lots.

Usage:
    python scripts/run_ft_eval.py --model ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v2:Dc21j4CJ --out data/reports/heldout_ftv2
    python scripts/run_ft_eval.py --model ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v3a:XXX --out data/reports/heldout_ftv3a

Uses same system prompt as training data. Produces section-level inference
matching training format.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import click
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

RAW = ROOT / "data/raw/bulk"

# IDENTICAL to system prompt in training data (build_finetune_dataset_v3.py)
SYSTEM_PROMPT = """Ты — эксперт по комплаенсу в коммерческих закупках 223-ФЗ.
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


def load_env():
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


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


def predict_section(client, model: str, tender_id: str, section: str, text: str) -> list[dict]:
    """Run FT model on one section, return list of flags."""
    user_msg = (
        f"Tender ID: {tender_id}\n"
        f"Section: {section}\n\n"
        f"Текст секции:\n---\n{text[:4000]}\n---\n\n"
        f"Найди реальные признаки ограничения конкуренции."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = resp.choices[0].message.content
        return json.loads(content).get("flags", [])
    except Exception as e:
        print(f"    ERROR section {section}: {e}")
        return []


@click.command()
@click.option("--model", required=True, help="Fine-tuned model ID")
@click.option("--out", type=click.Path(path_type=Path), required=True, help="Output dir")
@click.option("--lots-file", type=click.Path(path_type=Path),
              default=ROOT / "data/eval/heldout_v3_lots.json")
def main(model: str, out: Path, lots_file: Path) -> None:
    load_env()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    out.mkdir(parents=True, exist_ok=True)
    lot_ids = json.loads(lots_file.read_text(encoding="utf-8"))["lots"]
    print(f"Heldout lots: {len(lot_ids)}")
    print(f"Model: {model}")
    print(f"Output: {out}")
    print()

    summary = []
    t_total = time.time()

    for i, lot_id in enumerate(lot_ids, 1):
        out_file = out / f"{lot_id}.json"
        if out_file.exists():
            print(f"[{i}/{len(lot_ids)}] skip {lot_id} (exists)")
            r = json.loads(out_file.read_text(encoding="utf-8"))
            summary.append({
                "tender_id": lot_id,
                "n_flags": len(r.get("flags", [])),
                "labels": sorted({f["label"] for f in r.get("flags", [])}),
            })
            continue

        sections = gather_sections(lot_id)
        if not sections:
            print(f"[{i}/{len(lot_ids)}] no text {lot_id}")
            continue

        all_flags = []
        for section, text in sections.items():
            if len(text) < 100:
                continue
            t0 = time.time()
            flags = predict_section(client, model, lot_id, section, text)
            dt = time.time() - t0
            for f in flags:
                f["section"] = section  # ensure section is set
                all_flags.append(f)
            if flags:
                print(f"[{i}/{len(lot_ids)}] {lot_id} {section}: {len(flags)} flags ({dt:.1f}s)")

        report = {
            "tender_id": lot_id,
            "model": model,
            "flags": all_flags,
        }
        out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary.append({
            "tender_id": lot_id,
            "n_flags": len(all_flags),
            "labels": sorted({f["label"] for f in all_flags}),
        })

    (out / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone in {time.time() - t_total:.0f}s")
    total_flags = sum(s["n_flags"] for s in summary)
    print(f"Total flags across {len(summary)} lots: {total_flags}")
    from collections import Counter
    label_count = Counter()
    for s in summary:
        for l in s["labels"]:
            label_count[l] += 1
    print(f"Lots with each label: {dict(label_count)}")


if __name__ == "__main__":
    main()
