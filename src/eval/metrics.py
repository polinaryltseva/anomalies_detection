"""Метрики для multi-label классификации + span-level overlap.

Используем sklearn для классики и собственную реализацию IoU по span-ам.
Все метрики — per-label + macro/micro aggregation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from tender_anomaly.models.schema import LABELS, Flag


@dataclass
class LabelMetric:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class EvalReport:
    per_label: list[LabelMetric]
    macro_f1: float
    micro_f1: float
    weighted_f1: float
    span_iou_mean: float
    n_documents: int
    n_predictions: int
    n_gold_flags: int

    def as_table(self) -> str:
        rows = ["| Label | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        for m in self.per_label:
            rows.append(
                f"| `{m.label}` | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} | {m.support} |"
            )
        rows.append(
            f"| **Macro avg** | — | — | **{self.macro_f1:.3f}** | {self.n_gold_flags} |"
        )
        rows.append(
            f"| **Micro avg** | — | — | **{self.micro_f1:.3f}** | {self.n_gold_flags} |"
        )
        rows.append(f"\nMean span IoU: **{self.span_iou_mean:.3f}**")
        rows.append(f"Documents: {self.n_documents} | Pred flags: {self.n_predictions} | Gold flags: {self.n_gold_flags}")
        return "\n".join(rows)


def _doc_label_vector(flags: list[Flag]) -> np.ndarray:
    """Бинарный вектор присутствия каждой метки на уровне документа."""
    vec = np.zeros(len(LABELS), dtype=int)
    for f in flags:
        if f.label in LABELS:
            vec[LABELS.index(f.label)] = 1
    return vec


def _span_iou(span_a: str, span_b: str) -> float:
    """Грубый IoU на уровне токенов (split по whitespace).
    Достаточно для черновой оценки качества span extraction."""
    if not span_a or not span_b:
        return 0.0
    ta = set(span_a.lower().split())
    tb = set(span_b.lower().split())
    if not (ta | tb):
        return 0.0
    return len(ta & tb) / len(ta | tb)


def evaluate(
    predictions: dict[str, list[Flag]],
    gold: dict[str, list[Flag]],
) -> EvalReport:
    """Сравнивает predictions vs gold по lot_id.

    На уровне документа считаем мульти-лейбл F1 (есть ли метка X хоть один раз).
    На уровне span-ов — лучший IoU матчинг по предсказаниям, у которых правильная метка.
    """
    doc_ids = sorted(set(predictions) | set(gold))
    if not doc_ids:
        raise ValueError("Пустые predictions и gold")

    y_pred = np.zeros((len(doc_ids), len(LABELS)), dtype=int)
    y_true = np.zeros((len(doc_ids), len(LABELS)), dtype=int)
    for i, doc_id in enumerate(doc_ids):
        y_pred[i] = _doc_label_vector(predictions.get(doc_id, []))
        y_true[i] = _doc_label_vector(gold.get(doc_id, []))

    per_label: list[LabelMetric] = []
    for j, lbl in enumerate(LABELS):
        if y_true[:, j].sum() == 0 and y_pred[:, j].sum() == 0:
            per_label.append(LabelMetric(lbl, 0.0, 0.0, 0.0, 0))
            continue
        per_label.append(
            LabelMetric(
                label=lbl,
                precision=float(precision_score(y_true[:, j], y_pred[:, j], zero_division=0)),
                recall=float(recall_score(y_true[:, j], y_pred[:, j], zero_division=0)),
                f1=float(f1_score(y_true[:, j], y_pred[:, j], zero_division=0)),
                support=int(y_true[:, j].sum()),
            )
        )

    macro = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    micro = float(f1_score(y_true, y_pred, average="micro", zero_division=0))
    weighted = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    # Span IoU — для тех doc-ов, где метка корректно предсказана,
    # ищем лучшую пару (pred_span, gold_span) одной и той же метки.
    ious: list[float] = []
    for doc_id in doc_ids:
        pred_by_label: dict[str, list[Flag]] = defaultdict(list)
        gold_by_label: dict[str, list[Flag]] = defaultdict(list)
        for f in predictions.get(doc_id, []):
            pred_by_label[f.label].append(f)
        for f in gold.get(doc_id, []):
            gold_by_label[f.label].append(f)
        for lbl in set(pred_by_label) & set(gold_by_label):
            for gf in gold_by_label[lbl]:
                best = max(
                    (_span_iou(pf.span_text, gf.span_text) for pf in pred_by_label[lbl]),
                    default=0.0,
                )
                ious.append(best)

    return EvalReport(
        per_label=per_label,
        macro_f1=macro,
        micro_f1=micro,
        weighted_f1=weighted,
        span_iou_mean=float(np.mean(ious)) if ious else 0.0,
        n_documents=len(doc_ids),
        n_predictions=sum(len(v) for v in predictions.values()),
        n_gold_flags=sum(len(v) for v in gold.values()),
    )


def risk_ranking_auc(
    risk_scores: dict[str, float],
    gold: dict[str, list[Flag]],
) -> float | None:
    """ROC-AUC по бинарной метке «есть хоть одна gold-аномалия» vs risk_score.
    Возвращает None если в gold нет ни положительных, ни отрицательных примеров."""
    doc_ids = sorted(set(risk_scores) & set(gold))
    if not doc_ids:
        return None
    y_true = np.array([1 if gold[d] else 0 for d in doc_ids])
    y_score = np.array([risk_scores[d] for d in doc_ids])
    if len(set(y_true)) < 2:
        return None
    return float(roc_auc_score(y_true, y_score))
