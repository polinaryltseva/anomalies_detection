"""V2 + two-stage validation на подмножестве 10 «горячих» лотов
(top-3 + 7 signal lots с TRUE/PARTIAL).

Цель: оценить добавит ли two-stage заметную precision-bump поверх v2+gate.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.models.baseline_llm.openai_predictor_v2 import (  # noqa: E402
    OpenAIBaselinePredictorV2,
)
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("v2_2s")

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_v2_2stage"
OUT.mkdir(parents=True, exist_ok=True)

# Same 10-lot subset (signal + 3 top-risk)
def _load_subset() -> list[str]:
    """Same 30-lot subset as run_v2_subset.py for direct comparison."""
    import random
    random.seed(42)
    summaries = []
    REP = ROOT / "data/reports/bulk"
    for p in sorted(REP.glob("*.json")):
        if p.name == "_summary.json":
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("flags"):
                summaries.append((r["tender_id"], r["overall_risk_score"]))
        except Exception:
            continue
    summaries.sort(key=lambda x: x[1])

    ANN_F = ROOT / "data/labeled/bulk_flag_annotations.jsonl"
    ann = [json.loads(l) for l in ANN_F.read_text(encoding="utf-8").splitlines()]
    signal_lots = sorted({a["tender_id"] for a in ann if a["verdict"] in ("TRUE", "PARTIAL")})

    bottom = [t for t, _ in summaries[:8]]
    excluded = set(signal_lots) | set(bottom)
    top_pool = [t for t, s in summaries if s >= 0.95 and t not in excluded]
    random.shuffle(top_pool)
    top = top_pool[:10]
    return list(dict.fromkeys(signal_lots + bottom + top))[:30]


LOTS = _load_subset()


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
    predictor = OpenAIBaselinePredictorV2(
        model="gpt-4o-mini",
        two_stage=True,
        section_gating=True,
    )
    log.info("predictor: %s", predictor.method_id)

    summary = []
    t_total = time.time()
    for i, lot_id in enumerate(LOTS, 1):
        out_file = OUT / f"{lot_id}.json"
        if out_file.exists():
            log.info("[%d/%d] skip %s (exists)", i, len(LOTS), lot_id)
            continue
        sections = gather(lot_id)
        if not sections:
            log.warning("[%d/%d] skip %s (empty)", i, len(LOTS), lot_id)
            continue
        log.info("[%d/%d] %s — %d sections", i, len(LOTS), lot_id, len(sections))
        t0 = time.time()
        try:
            report = predictor.predict_document(tender_id=lot_id, sections=sections)
        except Exception as exc:  # noqa: BLE001
            log.error("[%d/%d] FAIL %s: %s", i, len(LOTS), lot_id, exc)
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
