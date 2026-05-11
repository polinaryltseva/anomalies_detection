"""V3 + 2-stage on ALL 200 lots in data/raw/bulk/ (resumable).

Skips lots already processed in data/reports/bulk_v3/.
Generates statistical-mass results for VKR.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.models.baseline_llm.openai_predictor_v3 import OpenAIBaselinePredictorV3  # noqa: E402
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v3full")

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_v3"
OUT.mkdir(parents=True, exist_ok=True)


def gather(lot_id: str) -> dict[str, str]:
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


def main() -> None:
    all_lots = sorted([d.name for d in RAW.iterdir() if d.is_dir()])
    log.info("Total lots: %d", len(all_lots))

    predictor = OpenAIBaselinePredictorV3(
        model="gpt-4o-mini",
        two_stage=True,
        section_gating=True,
    )
    log.info("predictor: %s", predictor.method_id)

    summary = []
    t_total = time.time()
    skipped = 0
    processed = 0

    for i, lot_id in enumerate(all_lots, 1):
        out_file = OUT / f"{lot_id}.json"
        if out_file.exists():
            skipped += 1
            continue

        sections = gather(lot_id)
        if not sections or sum(len(v) for v in sections.values()) < 100:
            log.warning("[%d/%d] skip empty %s", i, len(all_lots), lot_id)
            continue

        log.info("[%d/%d] %s — %d sections, %d chars",
                 i, len(all_lots), lot_id, len(sections), sum(len(v) for v in sections.values()))
        t0 = time.time()
        try:
            report = predictor.predict_document(tender_id=lot_id, sections=sections)
        except Exception as exc:  # noqa: BLE001
            log.error("FAIL %s: %s", lot_id, exc)
            continue
        dt = time.time() - t0
        out_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        log.info("  -> risk=%.2f flags=%d (%.1fs)",
                 report.overall_risk_score, len(report.flags), dt)
        summary.append({
            "tender_id": lot_id, "risk_score": report.overall_risk_score,
            "n_flags": len(report.flags), "method": report.method, "dt": round(dt, 1),
        })
        processed += 1

    # Update or create summary
    summary_path = OUT / "_summary.json"
    if summary_path.exists():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        existing.extend(summary)
        summary = existing
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("Done. processed=%d skipped(existing)=%d in %.1fs",
             processed, skipped, time.time() - t_total)


if __name__ == "__main__":
    main()
