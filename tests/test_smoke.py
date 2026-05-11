"""Smoke-тесты, которые не требуют сети/API."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_imports():
    from tender_anomaly import config  # noqa: F401
    from tender_anomaly.eval.metrics import evaluate  # noqa: F401
    from tender_anomaly.ingest.marker_client import MarkerClient  # noqa: F401
    from tender_anomaly.models.baseline_llm.prompts import build_system_blocks  # noqa: F401
    from tender_anomaly.models.schema import LABELS  # noqa: F401
    from tender_anomaly.parse.segmenter import segment  # noqa: F401


def test_segmenter_finds_sections():
    from tender_anomaly.parse.segmenter import merge_sections, segment

    sample = """
    ТЕХНИЧЕСКОЕ ЗАДАНИЕ
    Поставка ноутбуков MacBook Pro M3, 14 дюймов.

    ТРЕБОВАНИЯ К УЧАСТНИКАМ ЗАКУПКИ
    Опыт исполнения аналогичных контрактов 15 000 000 рублей.

    КРИТЕРИИ И ПОРЯДОК ОЦЕНКИ ЗАЯВОК
    Качество — оценивается комиссией.

    ПРОЕКТ ДОГОВОРА
    Оплата — 180 дней.
    """
    secs = merge_sections(segment(sample))
    assert "tz" in secs
    assert "requirements" in secs
    assert "evaluation" in secs
    assert "contract" in secs


def test_metrics_perfect_match():
    from tender_anomaly.eval.metrics import evaluate
    from tender_anomaly.models.schema import Flag

    gold = {
        "lot1": [Flag(label="brand_or_model_targeting", section="tz",
                      span_text="Apple MacBook", confidence=1.0,
                      rationale="x", regulatory_reference="Art. 42(4)")],
        "lot2": [],
    }
    pred = {
        "lot1": [Flag(label="brand_or_model_targeting", section="tz",
                      span_text="Apple MacBook Pro", confidence=0.9,
                      rationale="x", regulatory_reference="Art. 42(4)")],
        "lot2": [],
    }
    rep = evaluate(pred, gold)
    assert rep.macro_f1 > 0
    bm = next(m for m in rep.per_label if m.label == "brand_or_model_targeting")
    assert bm.precision == 1.0 and bm.recall == 1.0
    assert rep.span_iou_mean > 0.5  # "Apple MacBook" vs "Apple MacBook Pro"


def test_metrics_completely_wrong():
    from tender_anomaly.eval.metrics import evaluate
    from tender_anomaly.models.schema import Flag

    gold = {"lot1": [Flag(label="restrictive_tech_specs", section="tz",
                          span_text="x", confidence=1.0, rationale="x",
                          regulatory_reference="Art. 42(2)")]}
    pred = {"lot1": [Flag(label="ambiguous_evaluation_criteria", section="evaluation",
                          span_text="y", confidence=0.9, rationale="y",
                          regulatory_reference="Art. 67(4)")]}
    rep = evaluate(pred, gold)
    assert rep.macro_f1 < 0.3
