"""Run fine-tuned gpt-4.1 on 10 signal lots для сравнения."""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.models.baseline_llm.openai_predictor_ft import FineTunedPredictor  # noqa: E402
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ft")

RAW = ROOT / "data/raw/bulk"
OUT = ROOT / "data/reports/bulk_ft"
OUT.mkdir(parents=True, exist_ok=True)

# Read fine-tuned model name
job_info = json.loads((ROOT / "data/finetune/job_info.json").read_text(encoding="utf-8"))
FT_MODEL = job_info.get("fine_tuned_model")
if not FT_MODEL:
    # Get from job query
    from openai import OpenAI
    import os
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    j = client.fine_tuning.jobs.retrieve(job_info["job_id"])
    FT_MODEL = j.fine_tuned_model

log.info("Fine-tuned model: %s", FT_MODEL)

LOTS = [
    # Signal lots
    "169592487", "169618056", "169625341", "169625660", "169629574",
    "169638071", "169638083", "169642564",
    "169596304", "169625733",
    # Bottom-10 (manually verified clean)
    "169629544", "169596415", "169608004", "169633366", "169618156",
    "169608015", "169633302", "169618157", "169625477", "169629441",
    # HELD-OUT lots (NOT in training data) — for unbiased generalization test
    "169601988", "169625654", "169607912", "169633468", "169608001",
    "169596411", "169633409", "169629628", "169632529", "169618150",
    "169614080", "169632308", "169625569", "169618154", "169548312",
    "169638017", "169633404", "169602026", "169568252", "169629511",
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
    predictor = FineTunedPredictor(model=FT_MODEL)

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
