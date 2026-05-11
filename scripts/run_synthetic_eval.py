"""Прогон LLM-baseline на синтетическом seed-наборе и сравнение с gold-метками.

Фикстура: tests/fixtures/synthetic_eval.jsonl — 30 размеченных вручную (Claude)
синтетических секций тендеров, покрывающих все 8 меток codebook v1.0.

Запуск:
    python scripts/run_synthetic_eval.py                       # default openai
    python scripts/run_synthetic_eval.py --provider anthropic
    python scripts/run_synthetic_eval.py --model gpt-4o-mini
    python scripts/run_synthetic_eval.py --max-lots 5          # для быстрой пробы
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

from tender_anomaly.eval.metrics import evaluate, risk_ranking_auc  # noqa: E402
from tender_anomaly.models.baseline_llm import make_predictor  # noqa: E402
from tender_anomaly.models.schema import Flag  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_eval.jsonl"


def _load_fixture(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _gold_flags(record: dict) -> list[Flag]:
    return [Flag(**f) for f in record.get("gold_flags", [])]


@click.command()
@click.option("--fixture", type=click.Path(exists=True, path_type=Path), default=FIXTURE)
@click.option("--out", type=click.Path(path_type=Path), default=ROOT / "data/reports/synthetic")
@click.option("--max-lots", type=int, default=None, help="Ограничить число лотов для скорости")
@click.option("--provider", type=click.Choice(["openai", "anthropic"]), default=None)
@click.option("--model", type=str, default=None)
def main(fixture: Path, out: Path, max_lots: int | None, provider: str | None, model: str | None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("synthetic_eval")

    out.mkdir(parents=True, exist_ok=True)
    records = _load_fixture(fixture)
    if max_lots is not None:
        records = records[:max_lots]
    log.info("Loaded %d synthetic lots from %s", len(records), fixture.name)

    predictor = make_predictor(provider=provider, model=model)
    log.info("Using %s", predictor.method_id)

    predictions: dict[str, list[Flag]] = {}
    risk_scores: dict[str, float] = {}
    gold: dict[str, list[Flag]] = {}

    t0 = time.time()
    for i, rec in enumerate(records, 1):
        lot_id = rec["lot_id"]
        gold[lot_id] = _gold_flags(rec)

        report = predictor.predict_document(tender_id=lot_id, sections=rec["sections"])
        predictions[lot_id] = report.flags
        risk_scores[lot_id] = report.overall_risk_score

        # Сохранить per-lot отчёт для ручного просмотра
        (out / f"{lot_id}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        log.info(
            "[%d/%d] %s — pred:%d gold:%d risk:%.2f",
            i, len(records), lot_id, len(report.flags), len(gold[lot_id]), report.overall_risk_score,
        )

    total_dt = time.time() - t0

    # Метрики
    rep = evaluate(predictions, gold)
    auc = risk_ranking_auc(risk_scores, gold)

    summary = {
        "method": predictor.method_id,
        "n_lots": len(records),
        "total_time_sec": round(total_dt, 1),
        "avg_time_per_lot_sec": round(total_dt / len(records), 1),
        "macro_f1": round(rep.macro_f1, 3),
        "micro_f1": round(rep.micro_f1, 3),
        "weighted_f1": round(rep.weighted_f1, 3),
        "span_iou_mean": round(rep.span_iou_mean, 3),
        "risk_ranking_auc": round(auc, 3) if auc is not None else None,
        "n_predicted_flags": rep.n_predictions,
        "n_gold_flags": rep.n_gold_flags,
        "per_label": [
            {"label": m.label, "precision": round(m.precision, 3), "recall": round(m.recall, 3),
             "f1": round(m.f1, 3), "support": m.support}
            for m in rep.per_label
        ],
    }
    (out / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 70)
    print(f"Method: {summary['method']}")
    print(f"Lots: {summary['n_lots']}  Time: {summary['total_time_sec']}s "
          f"({summary['avg_time_per_lot_sec']}s/lot)")
    print("=" * 70)
    print(rep.as_table())
    if auc is not None:
        print(f"\nRisk-ranking ROC-AUC: {auc:.3f}")
    print(f"\nReports saved to: {out}")
    print(f"Summary: {out}/_summary.json")


if __name__ == "__main__":
    main()
