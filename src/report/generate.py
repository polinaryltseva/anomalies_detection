"""End-to-end: lot_id из manifest → загрузка файлов → парсинг → сегментация
→ LLM baseline → risk report.

Запуск:
    python -m tender_anomaly.report.generate \\
        --manifest data/raw/violations/manifest.jsonl \\
        --out data/reports/baseline_v1 \\
        --max-lots 10 \\
        --concat-files
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from tender_anomaly.config import RAW_DIR
from tender_anomaly.models.baseline_llm import BaselinePredictor, make_predictor
from tender_anomaly.models.schema import RiskReport
from tender_anomaly.parse.extractor import extract
from tender_anomaly.parse.segmenter import merge_sections, segment

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _process_lot(
    record: dict,
    raw_root: Path,
    predictor: BaselinePredictor,
    concat_files: bool,
) -> RiskReport | None:
    lot_id = record["lot_id"]
    files = record.get("downloaded_files") or []
    if not files:
        log.warning("lot %s: нет скачанных файлов в manifest", lot_id)
        return None

    sections_acc: dict[str, list[str]] = {}
    for rel in files:
        path = raw_root / rel
        if not path.exists():
            log.warning("lot %s: файл не найден %s", lot_id, path)
            continue
        ed = extract(path)
        if ed.error or not ed.text:
            log.info("lot %s: пропуск %s (%s)", lot_id, path.name, ed.error or "empty")
            continue
        if concat_files:
            sections_acc.setdefault("unsegmented", []).append(ed.text)
        else:
            for sec_name, sec_text in merge_sections(segment(ed.text)).items():
                sections_acc.setdefault(sec_name, []).append(sec_text)

    if not sections_acc:
        log.warning("lot %s: ни одного парсимого файла", lot_id)
        return None

    sections = {k: "\n\n".join(v) for k, v in sections_acc.items()}
    return predictor.predict_document(tender_id=str(lot_id), sections=sections)


@click.command()
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--max-lots", type=int, default=10, show_default=True)
@click.option("--concat-files", is_flag=True, help="Не сегментировать; всё в unsegmented")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic"]),
    default=None,
    help="LLM провайдер (default: из LLM_PROVIDER env, иначе openai)",
)
@click.option("--model", type=str, default=None, help="Override default model (e.g. gpt-4o-mini)")
def main(
    manifest: Path,
    out: Path,
    max_lots: int,
    concat_files: bool,
    provider: str | None,
    model: str | None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    raw_root = manifest.parent

    records = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    log.info("manifest: %d лотов; обрабатываем %d", len(records), min(max_lots, len(records)))

    predictor = make_predictor(provider=provider, model=model)
    log.info("provider/model: %s", predictor.method_id)

    summaries = []
    for record in records[:max_lots]:
        # Skip if report already exists (resumable runs)
        out_path = out / f"{record['lot_id']}.json"
        if out_path.exists():
            log.info("[skip] lot %s already has report", record["lot_id"])
            continue
        try:
            report = _process_lot(record, raw_root, predictor, concat_files)
        except Exception as exc:  # noqa: BLE001
            log.warning("lot %s: SKIPPED due to error: %s", record["lot_id"], exc)
            continue
        if report is None:
            continue
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        log.info(
            "[%s] risk=%.2f level=%s flags=%d",
            report.tender_id, report.overall_risk_score, report.risk_level, len(report.flags),
        )
        summaries.append({
            "tender_id": report.tender_id,
            "risk_score": report.overall_risk_score,
            "risk_level": report.risk_level,
            "n_flags": len(report.flags),
            "labels": sorted({f.label for f in report.flags}),
        })

    summary_path = out / "_summary.json"
    summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("done. %d reports → %s", len(summaries), out)


if __name__ == "__main__":
    main()
