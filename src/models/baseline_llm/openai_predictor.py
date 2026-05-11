"""LLM-baseline на OpenAI Chat Completions API + structured output (Pydantic).

OpenAI кэширует промпт-префикс автоматически когда он >1024 токенов и повторяется —
никаких маркеров в коде не нужно. `prompt_cache_key` помогает шардировать кэш по типам
запросов; используем стабильное значение для лучшего hit rate.
"""

from __future__ import annotations

import logging
import math
import time

from openai import APIError, BadRequestError, OpenAI
from pydantic import BaseModel, Field

from tender_anomaly.config import OPENAI
from tender_anomaly.models.baseline_llm.prompts import (
    build_system_text,
    build_user_message,
)
from tender_anomaly.models.schema import Flag, RiskReport, SectionPrediction

log = logging.getLogger(__name__)


class _SectionResult(BaseModel):
    """JSON-схема ответа модели на одну секцию."""
    flags: list[Flag] = Field(default_factory=list)


class OpenAIBaselinePredictor:
    """OpenAI-вариант LLM baseline. Совместим по интерфейсу с Anthropic-вариантом."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model or OPENAI.model
        api_key = api_key or OPENAI.api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY не задан в .env")
        self.client = OpenAI(api_key=api_key)
        self.max_tokens = max_tokens
        self.method_id = f"llm_baseline:{self.model}"
        # Cache shard key — стабильный, чтобы все вызовы по этому codebook v1
        # делили один и тот же кэш-сегмент (повышает hit rate).
        self._cache_key = "tender-anomaly-codebook-v1"

    def predict_section(
        self,
        tender_id: str,
        section: str,
        text: str,
        retries: int = 5,
    ) -> SectionPrediction:
        """Один вызов на одну секцию. Кидает APIError после исчерпания retries —
        это сигнал orchestrator-у что лот не обработан и не надо сохранять пустой stub."""
        if not text.strip():
            return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                completion = self.client.chat.completions.parse(
                    model=self.model,
                    max_completion_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": build_system_text()},
                        {"role": "user", "content": build_user_message(tender_id, section, text)},
                    ],
                    response_format=_SectionResult,
                    extra_body={"prompt_cache_key": self._cache_key},
                )
                break
            except BadRequestError as exc:
                # 400 — не ретраим, конкретная секция реально невалидна
                log.error("OpenAI bad request for %s/%s: %s", tender_id, section, exc)
                return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]
            except APIError as exc:
                last_exc = exc
                wait = 5 * (2 ** attempt)  # 5, 10, 20, 40, 80 сек
                log.warning(
                    "OpenAI API error %s/%s (attempt %d/%d), sleeping %ds: %s",
                    tender_id, section, attempt + 1, retries, wait, exc,
                )
                time.sleep(wait)
        else:
            # Все retries провалились — подымаем, чтобы predict_document не сохранял пустой отчёт
            raise RuntimeError(
                f"OpenAI failed {retries}× on {tender_id}/{section}: {last_exc}"
            ) from last_exc

        usage = completion.usage
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        log.debug(
            "tokens prompt=%d cached=%d completion=%d",
            usage.prompt_tokens, cached, usage.completion_tokens,
        )

        msg = completion.choices[0].message
        if msg.refusal:
            log.warning("model refused: %s", msg.refusal)
            return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]
        parsed: _SectionResult = msg.parsed
        if parsed is None:
            return SectionPrediction(section=section, flags=[])  # type: ignore[arg-type]

        for f in parsed.flags:
            f.section = section  # type: ignore[assignment]
        return SectionPrediction(section=section, flags=parsed.flags)  # type: ignore[arg-type]

    def predict_document(
        self,
        tender_id: str,
        sections: dict[str, str],
    ) -> RiskReport:
        all_flags: list[Flag] = []
        for sec_name, sec_text in sections.items():
            pred = self.predict_section(tender_id, sec_name, sec_text)
            all_flags.extend(pred.flags)
        risk_score = round(1.0 - math.exp(-sum(f.confidence for f in all_flags)), 3)
        if risk_score >= 0.7:
            level = "high"
        elif risk_score >= 0.3:
            level = "medium"
        else:
            level = "low"
        return RiskReport(
            tender_id=tender_id,
            overall_risk_score=risk_score,
            risk_level=level,
            flags=all_flags,
            method=self.method_id,
        )
