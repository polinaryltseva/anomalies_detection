"""LLM baseline для fine-tuned модели — использует SHORT system prompt
(тот же что в training data), без 2-stage validation (модель уже обучена
делать whitelist filtering сама)."""

from __future__ import annotations

import logging
import math
import time

from openai import APIError, BadRequestError, OpenAI
from pydantic import BaseModel, Field

from tender_anomaly.config import OPENAI
from tender_anomaly.models.schema import Flag, RiskReport, SectionPrediction

log = logging.getLogger(__name__)


SHORT_SYSTEM = """Ты — эксперт по комплаенсу в коммерческих закупках 223-ФЗ.
Прочитай фрагмент тендерной документации и найди РЕАЛЬНЫЕ признаки ограничения
конкуренции. Игнорируй стандартные обязательные нормы 223-ФЗ (анти-COI клаузула,
СМП-only режим, Russian origin priority, стандартные сроки 5/4/25/7/10 дней,
бренд С «или эквивалент», описания структуры заявки, цитаты статей закона).

Флагать только: брендинг без эквивалента, экстремальные сроки оплаты ≥120 дн,
прямой бан слов «или эквивалент», пустые критерии оценки, конкретные ФИО
аффилированных лиц.

Возвращай JSON: {"flags": [{"label", "section", "span_text", "confidence",
"rationale", "regulatory_reference"}, ...]}. Если признаков нет — пустой массив.

Метки: brand_or_model_targeting, restrictive_tech_specs,
disproportionate_qualification, documentary_burden, ambiguous_evaluation_criteria,
unusual_short_deadlines, unusual_contract_terms, conflict_of_interest_signals.
"""


class _SectionResult(BaseModel):
    flags: list[Flag] = Field(default_factory=list)


class FineTunedPredictor:
    """Predictor for our fine-tuned model. No 2-stage validation —
    model has codebook v3 baked into weights."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        api_key = api_key or OPENAI.api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY не задан")
        self.client = OpenAI(api_key=api_key)
        self.max_tokens = max_tokens
        self.method_id = f"llm_baseline:{model}:ft"
        self._cache_key = "tender-anomaly-ft-v1"

    def predict_section(self, tender_id: str, section: str, text: str) -> SectionPrediction:
        if not text.strip():
            return SectionPrediction(section=section, flags=[])

        text = text[:4000]
        user = (
            f"Tender ID: {tender_id}\n"
            f"Section: {section}\n\n"
            f"Текст секции:\n---\n{text}\n---\n\n"
            f"Найди реальные признаки ограничения конкуренции."
        )

        last_exc = None
        for attempt in range(5):
            try:
                completion = self.client.chat.completions.parse(
                    model=self.model,
                    max_completion_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": SHORT_SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    response_format=_SectionResult,
                    extra_body={"prompt_cache_key": self._cache_key},
                )
                break
            except BadRequestError as exc:
                log.error("bad request: %s", exc)
                return SectionPrediction(section=section, flags=[])
            except APIError as exc:
                last_exc = exc
                wait = 5 * (2 ** attempt)
                log.warning("API error attempt %d/5, sleeping %ds", attempt + 1, wait)
                time.sleep(wait)
        else:
            raise RuntimeError(f"OpenAI failed: {last_exc}")

        msg = completion.choices[0].message
        if msg.refusal or msg.parsed is None:
            return SectionPrediction(section=section, flags=[])
        for f in msg.parsed.flags:
            f.section = section
        return SectionPrediction(section=section, flags=msg.parsed.flags)

    def predict_document(self, tender_id: str, sections: dict[str, str]) -> RiskReport:
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
