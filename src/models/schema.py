"""Pydantic-схема risk report и flag-а — единая для всех моделей и для evaluation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LABELS: tuple[str, ...] = (
    "restrictive_tech_specs",
    "brand_or_model_targeting",
    "disproportionate_qualification",
    "ambiguous_evaluation_criteria",
    "unusual_short_deadlines",
    "unusual_contract_terms",
    "documentary_burden",
    "conflict_of_interest_signals",
)

LabelLiteral = Literal[
    "restrictive_tech_specs",
    "brand_or_model_targeting",
    "disproportionate_qualification",
    "ambiguous_evaluation_criteria",
    "unusual_short_deadlines",
    "unusual_contract_terms",
    "documentary_burden",
    "conflict_of_interest_signals",
]

SectionLiteral = Literal[
    "preamble",
    "tz",
    "evaluation",
    "requirements",
    "contract",
    "procedure",
    "pricing",
    "unsegmented",
]


class Flag(BaseModel):
    """Один обнаруженный признак ограничения конкуренции."""

    label: LabelLiteral = Field(description="Метка из таксономии codebook v1.0")
    section: SectionLiteral = Field(description="Секция документа, в которой обнаружено")
    span_text: str = Field(description="Дословная цитата из текста (≤300 символов)")
    confidence: float = Field(ge=0.0, le=1.0, description="Уверенность модели [0..1]")
    rationale: str = Field(description="Объяснение, почему это признак (≤500 символов)")
    regulatory_reference: str = Field(
        description="Конкретный пункт регулирования (например, 'EU Directive 2014/24/EU Art. 42(4)')"
    )


class RiskReport(BaseModel):
    """Полный отчёт по одному документу/лоту."""

    tender_id: str
    overall_risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    flags: list[Flag] = Field(default_factory=list)
    method: str = Field(description="Идентификатор модели/метода, который сгенерировал отчёт")


class SectionPrediction(BaseModel):
    """Предсказание для одной секции (используется при оценке)."""

    section: SectionLiteral
    flags: list[Flag] = Field(default_factory=list)
