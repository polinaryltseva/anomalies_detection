"""End-to-end на реальных лотах из data/raw/manual/<lot_name>/.

1. Идёт по папкам — каждая папка = один лот.
2. Парсит все распознаваемые файлы (.docx/.pdf/.rtf/.xlsx/.xls).
3. Сегментирует объединённый текст лота на разделы.
4. Прогоняет LLM-baseline.
5. Сохраняет risk-report на лот + сводный summary.

Запуск:
    python scripts/run_real_lots.py
    python scripts/run_real_lots.py --provider openai --model gpt-4o
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.models.baseline_llm import make_predictor  # noqa: E402
from tender_anomaly.parse.extractor import extract  # noqa: E402
from tender_anomaly.parse.segmenter import merge_sections, segment  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("real_lots")

# Расширения, которые умеем парсить (игнорим .doc — пользователь конвертил их в .docx)
SUPPORTED_EXTS = {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}


def _gather_lot_text(lot_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Возвращает (sections, parsed_files). Объединяет тексты всех файлов
    лота, потом сегментирует один раз — секции получаются цельными."""
    parsed_files: list[str] = []
    parts: list[str] = []
    for f in sorted(lot_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        # Пропускаем .doc если рядом лежит .docx (конвертированная версия)
        if f.suffix.lower() == ".doc":
            if f.with_suffix(".docx").exists():
                continue
        ed = extract(f)
        if ed.error or not ed.text:
            log.warning("  skip %s: %s", f.name, ed.error or "empty")
            continue
        # Префикс с именем файла помогает сегментатору не сливать содержимое
        parts.append(f"\n\n=== Файл: {f.name} ===\n\n{ed.text}")
        parsed_files.append(f.name)

    full_text = "\n".join(parts)
    sections = merge_sections(segment(full_text))
    if not sections:
        sections = {"unsegmented": full_text}
    return sections, parsed_files


@click.command()
@click.option("--root", type=click.Path(exists=True, path_type=Path),
              default=ROOT / "data/raw/manual")
@click.option("--out", type=click.Path(path_type=Path),
              default=ROOT / "data/reports/real_lots")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default=None)
@click.option("--model", type=str, default=None)
def main(root: Path, out: Path, provider: str | None, model: str | None) -> None:
    out.mkdir(parents=True, exist_ok=True)

    lot_dirs = sorted([d for d in root.iterdir() if d.is_dir()])
    log.info("Found %d lot directories under %s", len(lot_dirs), root)

    predictor = make_predictor(provider=provider, model=model)
    log.info("Using %s", predictor.method_id)

    summary: list[dict] = []
    t_total = time.time()

    for lot_dir in lot_dirs:
        lot_id = lot_dir.name
        out_file = out / f"{lot_id}.json"
        # Resumable: пропускаем уже обработанные лоты
        if out_file.exists():
            log.info("[skip] %s already has report", lot_id)
            continue

        log.info("\n=== %s ===", lot_id)
        sections, files = _gather_lot_text(lot_dir)
        if not sections or sum(len(v) for v in sections.values()) < 100:
            log.warning("  skip: пусто после парсинга")
            continue

        # Логируем что нашли по разделам
        for k, v in sections.items():
            log.info("  section %s: %d chars", k, len(v))
        log.info("  parsed files: %s", files)

        t0 = time.time()
        try:
            report = predictor.predict_document(tender_id=lot_id, sections=sections)
        except Exception as exc:  # noqa: BLE001
            log.warning("  SKIP %s due to LLM error: %s", lot_id, exc)
            continue
        dt = time.time() - t0

        out_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        log.info("  risk=%.2f level=%s flags=%d (%.1fs)",
                 report.overall_risk_score, report.risk_level, len(report.flags), dt)
        for f in report.flags:
            log.info("    [%s] section=%s conf=%.2f span=«%s»",
                     f.label, f.section, f.confidence, f.span_text[:80])

        summary.append({
            "lot_id": lot_id,
            "risk_score": report.overall_risk_score,
            "risk_level": report.risk_level,
            "n_flags": len(report.flags),
            "labels": sorted({f.label for f in report.flags}),
            "n_files": len(files),
            "sections": sorted(sections.keys()),
            "predict_time_sec": round(dt, 1),
        })

    summary_path = out / "_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("\n=== TOTAL ===")
    log.info("Lots: %d  Time: %.1fs", len(summary), time.time() - t_total)
    log.info("Reports: %s", out)


if __name__ == "__main__":
    main()
