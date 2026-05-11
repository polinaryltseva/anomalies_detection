"""LLM-baseline предиктор. Принимает сегментированный документ → возвращает RiskReport.

Использует Claude Opus 4.7 (по умолчанию) с output_config.format для гарантированного
JSON и cache_control на системном промпте (codebook ~8К токенов).
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import BaseModel, Field

from tender_anomaly.config import ANTHROPIC
from tender_anomaly.models.baseline_llm.prompts import (
    build_system_blocks,
    build_user_message,
)
from tender_anomaly.models.schema import Flag, RiskReport, SectionPrediction

log = logging.getLogger(__name__)


class _SectionResult(BaseModel):
    """JSON-схема ответа модели на одну секцию."""
    flags: list[Flag] = Field(default_factory=list)


class LLMBaselinePredictor:
    """Запускает классификацию по секциям и собирает RiskReport."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model or ANTHROPIC.model
        api_key = api_key or ANTHROPIC.api_key
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY не задан в .env")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_tokens = max_tokens
        self.method_id = f"llm_baseline:{self.model}"

    def predict_section(
        self,
        tender_id: str,
        section: str,
        text: str,
    ) -> SectionPrediction:
        """Один LLM-вызов на одну секцию. Кэш системного промпта переиспользуется."""
        if not text.strip():
            return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]

        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=build_system_blocks(),
                messages=[{"role": "user", "content": build_user_message(tender_id, section, text)}],
                output_format=_SectionResult,
            )
        except anthropic.BadRequestError as exc:
            log.error("LLM bad request for %s/%s: %s", tender_id, section, exc)
            return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]

        usage = response.usage
        log.debug(
            "tokens in=%d cached_read=%d cached_write=%d out=%d",
            usage.input_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
            usage.output_tokens,
        )

        parsed: _SectionResult = response.parsed_output
        # Перезаписываем section в каждом флаге — модель могла перепутать
        for f in parsed.flags:
            f.section = section  # type: ignore[assignment]
        return SectionPrediction(section=section, flags=parsed.flags)  # type: ignore[arg-type]

    def predict_document(
        self,
        tender_id: str,
        sections: dict[str, str],
    ) -> RiskReport:
        """Прогон по всем секциям документа и сбор risk report."""
        all_flags: list[Flag] = []
        for sec_name, sec_text in sections.items():
            pred = self.predict_section(tender_id, sec_name, sec_text)
            all_flags.extend(pred.flags)

        # Risk score: взвешенная сумма уверенностей с насыщением
        risk_score = _aggregate_risk(all_flags)
        risk_level = _risk_level(risk_score)
        return RiskReport(
            tender_id=tender_id,
            overall_risk_score=risk_score,
            risk_level=risk_level,
            flags=all_flags,
            method=self.method_id,
        )


def _aggregate_risk(flags: list[Flag]) -> float:
    """1 - exp(-Σ confidence) — больше флагов → ближе к 1, насыщение."""
    import math
    s = sum(f.confidence for f in flags)
    return round(1.0 - math.exp(-s), 3)


def _risk_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"
