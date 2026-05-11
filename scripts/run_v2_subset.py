"""Прогон codebook v2 на стратифицированном подмножестве 30 лотов.

Стратегия отбора:
- 12 лотов с TRUE/PARTIAL флагами из v1 (проверка что v2 сохраняет сигнал)
- 8 bottom-risk лотов из bulk (проверка что v2 не флагает «чистые»)
- 10 случайных top-risk лотов (overall noise reduction)

Сохраняет в data/reports/bulk_v2/<lot_id>.json для прямого сравнения с
data/reports/bulk/<lot_id>.json (v1).

Запуск:
    python scripts/run_v2_subset.py [--two-stage] [--no-gate]
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.models.baseline_llm.openai_predictor_v2 import (  # noqa: E402
    OpenAIBaselinePredictorV2,
)
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v2run")

random.seed(42)

RAW = ROOT / "data/raw/bulk"
REPORTS_V1 = ROOT / "data/reports/bulk"
ANNOTATIONS = ROOT / "data/labeled/bulk_flag_annotations.jsonl"


def pick_subset() -> list[str]:
    """Вернёт 30 lot_ids: signal lots + bottom + top."""
    # 12 lots with TRUE/PARTIAL (signal preservation)
    ann = [json.loads(l) for l in ANNOTATIONS.read_text(encoding="utf-8").splitlines()]
    signal_lots = sorted({a["tender_id"] for a in ann if a["verdict"] in ("TRUE", "PARTIAL")})
    log.info("signal lots (TRUE/PARTIAL): %d", len(signal_lots))

    # Bottom 8 lots from v1 reports
    summaries = []
    for p in sorted(REPORTS_V1.glob("*.json")):
        if p.name == "_summary.json":
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("flags"):
                summaries.append((r["tender_id"], r["overall_risk_score"]))
        except Exception:
            continue
    summaries.sort(key=lambda x: x[1])
    bottom = [t for t, _ in summaries[:8]]
    log.info("bottom 8 lots: %s", bottom)

    # Top-risk 10 random (excluding signal_lots and bottom)
    excluded = set(signal_lots) | set(bottom)
    top_pool = [t for t, s in summaries if s >= 0.95 and t not in excluded]
    random.shuffle(top_pool)
    top = top_pool[:10]
    log.info("top 10 random lots: %s", top)

    subset = list(dict.fromkeys(signal_lots + bottom + top))[:30]
    return subset


def gather_lot(lot_id: str) -> dict[str, str]:
    d = RAW / lot_id
    if not d.exists():
        return {}
    parts: list[str] = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}:
            continue
        ed = extract(f)
        if ed.error or not ed.text:
            continue
        parts.append(f"\n\n=== {f.name} ===\n\n{ed.text}")
    full = "\n".join(parts)
    sections = merge_sections(segment(full))
    if not sections:
        sections = {"unsegmented": full}
    return sections


@click.command()
@click.option("--two-stage", is_flag=True, help="Включить второй проход валидации")
@click.option("--no-gate", is_flag=True, help="Отключить per-section gating")
@click.option("--out", type=click.Path(path_type=Path), default=ROOT / "data/reports/bulk_v2")
@click.option("--model", default="gpt-4o-mini")
def main(two_stage: bool, no_gate: bool, out: Path, model: str) -> None:
    out.mkdir(parents=True, exist_ok=True)

    subset = pick_subset()
    log.info("Subset size: %d lots", len(subset))

    predictor = OpenAIBaselinePredictorV2(
        model=model,
        two_stage=two_stage,
        section_gating=not no_gate,
    )
    log.info("predictor: %s", predictor.method_id)

    summary = []
    t_total = time.time()

    for i, lot_id in enumerate(subset, 1):
        out_file = out / f"{lot_id}.json"
        if out_file.exists():
            log.info("[%d/%d] skip %s (exists)", i, len(subset), lot_id)
            continue

        sections = gather_lot(lot_id)
        if not sections or sum(len(v) for v in sections.values()) < 100:
            log.warning("[%d/%d] skip %s (empty)", i, len(subset), lot_id)
            continue

        log.info("[%d/%d] %s — %d sections, %d chars",
                 i, len(subset), lot_id, len(sections), sum(len(v) for v in sections.values()))

        t0 = time.time()
        try:
            report = predictor.predict_document(tender_id=lot_id, sections=sections)
        except Exception as exc:  # noqa: BLE001
            log.error("[%d/%d] FAIL %s: %s", i, len(subset), lot_id, exc)
            continue
        dt = time.time() - t0

        out_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        log.info("  → risk=%.2f flags=%d (%.1fs)",
                 report.overall_risk_score, len(report.flags), dt)
        for f in report.flags[:5]:
            log.info("    [%s] %s «%s»", f.label, f.section, f.span_text[:80])

        summary.append({
            "tender_id": lot_id,
            "risk_score": report.overall_risk_score,
            "n_flags": len(report.flags),
            "labels": sorted({f.label for f in report.flags}),
            "method": report.method,
            "dt": round(dt, 1),
        })

    sp = out / "_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Total: %d lots, %.1fs", len(summary), time.time() - t_total)
    log.info("Reports → %s", out)


if __name__ == "__main__":
    main()
