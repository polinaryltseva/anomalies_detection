"""V3 codebook (W1-W15) + 2-stage validation на 30-lot subset."""
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
log = logging.getLogger("v3")

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_v3"
OUT.mkdir(parents=True, exist_ok=True)


def _load_subset() -> list[str]:
    """Same 30-lot subset as v2."""
    import random
    random.seed(42)
    REP = ROOT / "data/reports/bulk"
    summaries = []
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
    LOTS = _load_subset()
    predictor = OpenAIBaselinePredictorV3(
        model="gpt-4o-mini",
        two_stage=True,
        section_gating=True,
    )
    log.info("predictor: %s", predictor.method_id)
    log.info("lots: %d", len(LOTS))

    summary = []
    t_total = time.time()
    for i, lot_id in enumerate(LOTS, 1):
        out_file = OUT / f"{lot_id}.json"
        if out_file.exists():
            log.info("[%d/%d] skip %s", i, len(LOTS), lot_id)
            continue
        sections = gather(lot_id)
        if not sections or sum(len(v) for v in sections.values()) < 100:
            continue
        log.info("[%d/%d] %s", i, len(LOTS), lot_id)
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
