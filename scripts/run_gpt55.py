"""V3 codebook + 2-stage validation на gpt-5.5 (новейшая флагманская модель).

Сравниваем с gpt-4o-mini (наш baseline) на тех же 10 signal лотах.
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
log = logging.getLogger("gpt55")

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_gpt55"
OUT.mkdir(parents=True, exist_ok=True)

# 10 signal lots где есть TRUE/PARTIAL флаги
LOTS = [
    "169592487", "169618056", "169625341", "169625660", "169629574",
    "169638071", "169638083", "169642564",
    "169596304", "169625733",
]


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
    predictor = OpenAIBaselinePredictorV3(
        model="gpt-5.5",
        two_stage=True,
        section_gating=True,
    )
    log.info("predictor: %s", predictor.method_id)

    summary = []
    t_total = time.time()
    for i, lot_id in enumerate(LOTS, 1):
        out_file = OUT / f"{lot_id}.json"
        if out_file.exists():
            log.info("[%d/%d] skip %s", i, len(LOTS), lot_id)
            continue
        sections = gather(lot_id)
        if not sections:
            continue
        log.info("[%d/%d] %s -- %d sections", i, len(LOTS), lot_id, len(sections))
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

    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Done. %d lots in %.1fs", len(summary), time.time() - t_total)


if __name__ == "__main__":
    main()
