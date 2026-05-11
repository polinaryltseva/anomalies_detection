"""LLM baseline v3: codebook v3 + per-section gating + 2-stage validation
with W1-W15 whitelist."""

from __future__ import annotations

import logging
import math
import time

from openai import APIError, BadRequestError, OpenAI
from pydantic import BaseModel, Field

from tender_anomaly.config import OPENAI
from tender_anomaly.models.baseline_llm.prompts_v3 import (
    build_system_text_v3,
    build_user_message_v3,
)
from tender_anomaly.models.baseline_llm.prompts_v2 import SECTION_LABEL_WHITELIST
from tender_anomaly.models.schema import LABELS, Flag, RiskReport, SectionPrediction

log = logging.getLogger(__name__)


class _SectionResult(BaseModel):
    flags: list[Flag] = Field(default_factory=list)


class _ValidationResult(BaseModel):
    keep: bool
    reason: str


VALIDATION_SYSTEM_V3 = """Ты — second-pass валидатор флагов аномалий в 223-ФЗ закупках.
Тебе дают ОДИН флаг с контекстом. Твоя задача: проверить, не попадает ли он
в whitelist обязательных норм 223-ФЗ или нейтральных текстовых паттернов.

Whitelist (если ДА на любой пункт — keep=false):

W1. Анти-COI клаузула ст.3.1 («Отсутствие конфликта интересов, под которым
    понимаются случаи... состоят в браке... выгодоприобретателями...»).
W2. СМП-only режим («только субъекты малого и среднего предпринимательства»).
W3. Russian origin priority («товаров российского происхождения»).
W4. Стандартные сроки 5 дн.подп / 4 дн.изм / 25% налог / 7-10 дн. ст.3.4 ч.14.1.
W5. Бренд С «или эквивалент» в пределах 50 символов.
W6. Идентификаторы существующих объектов (VIN, госномер, инв.№, кадастр.№).
W7. Совместимость с имеющимся у заказчика оборудованием.
W8. Мета-юридический текст: «при наличии указания на товарный знак, заявка
    должна содержать...» — описание структуры заявки.
W9. Стандартные ст.3 ч.10 квал. требования (РНП, налоги, судимость, иноагенты).
W10. Аукцион electronic — единственный критерий цена.
W11. Структурные описания и заголовки разделов («Заявка состоит из двух частей»,
     «Требования к продукции», «Перечень документов»).
W12. Verbatim цитаты статей 223-ФЗ (с явным указанием «п.X ч.Y ст.Z ФЗ № 223»).
W13. Защитные правила в пользу участника (срок продлевается, право отозвать
     заявку, равная степень для всех участников).
W14. Определения терминов в глоссарии.
W15. Стандартные финансовые механизмы (1-5% обеспечение, 0,1% штраф/день,
     12-36 мес. гарантии, 7 раб.дн. оплата по этапу).

Если ВСЕ 15 пунктов — НЕТ → keep=true (это реальная аномалия).
Если хоть один — ДА → keep=false и укажи WX в reason.
"""


class OpenAIBaselinePredictorV3:
    """v3 предиктор с расширенным whitelist W1-W15."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4096,
        two_stage: bool = True,
        section_gating: bool = True,
        high_conf_skip: float = 1.01,  # default disabled (always run 2stage)
    ) -> None:
        self.model = model or OPENAI.model
        api_key = api_key or OPENAI.api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY не задан в .env")
        self.client = OpenAI(api_key=api_key)
        self.max_tokens = max_tokens
        self.two_stage = two_stage
        self.section_gating = section_gating
        self._high_conf_skip = high_conf_skip
        suffix = "v3"
        if section_gating:
            suffix += "+gate"
        if two_stage:
            suffix += "+2stage"
            if high_conf_skip < 1.0:
                suffix += f"(skip>={high_conf_skip})"
        self.method_id = f"llm_baseline:{self.model}:{suffix}"
        self._cache_key = "tender-anomaly-codebook-v3"

    def _call_with_retry(self, *, messages, response_format, retries: int = 5):
        last_exc = None
        for attempt in range(retries):
            try:
                return self.client.chat.completions.parse(
                    model=self.model,
                    max_completion_tokens=self.max_tokens,
                    messages=messages,
                    response_format=response_format,
                    extra_body={"prompt_cache_key": self._cache_key},
                )
            except BadRequestError as exc:
                log.error("OpenAI bad request: %s", exc)
                return None
            except APIError as exc:
                last_exc = exc
                wait = 5 * (2 ** attempt)
                log.warning("API error attempt %d/%d, sleeping %ds", attempt + 1, retries, wait)
                time.sleep(wait)
        raise RuntimeError(f"OpenAI failed {retries}×: {last_exc}") from last_exc

    def _validate_flag(self, flag: Flag, section: str, context: str) -> tuple[bool, str]:
        user = (
            f"Section: {section}\n"
            f"Label: {flag.label}\n"
            f"Span: «{flag.span_text}»\n"
            f"Rationale: {flag.rationale}\n"
            f"Regulatory ref: {flag.regulatory_reference}\n\n"
            f"Контекст вокруг span:\n---\n{context[:1500]}\n---\n\n"
            f"Прогони whitelist W1-W15. Это аномалия (keep=true) или whitelist (keep=false)?"
        )
        completion = self._call_with_retry(
            messages=[
                {"role": "system", "content": VALIDATION_SYSTEM_V3},
                {"role": "user", "content": user},
            ],
            response_format=_ValidationResult,
        )
        if completion is None:
            return True, "validation_call_failed"
        msg = completion.choices[0].message
        if msg.refusal or msg.parsed is None:
            return True, "validation_no_response"
        return msg.parsed.keep, msg.parsed.reason

    def predict_section(self, tender_id: str, section: str, text: str) -> SectionPrediction:
        if not text.strip():
            return SectionPrediction(section=section, flags=[])

        completion = self._call_with_retry(
            messages=[
                {"role": "system", "content": build_system_text_v3()},
                {"role": "user", "content": build_user_message_v3(tender_id, section, text)},
            ],
            response_format=_SectionResult,
        )
        if completion is None:
            return SectionPrediction(section=section, flags=[])

        msg = completion.choices[0].message
        if msg.refusal:
            return SectionPrediction(section=section, flags=[])
        parsed: _SectionResult | None = msg.parsed
        if parsed is None:
            return SectionPrediction(section=section, flags=[])

        for f in parsed.flags:
            f.section = section

        if self.section_gating:
            allowed = SECTION_LABEL_WHITELIST.get(section, set(LABELS))
            before = len(parsed.flags)
            parsed.flags = [f for f in parsed.flags if f.label in allowed]
            if before - len(parsed.flags):
                log.info("  [gate] %s: dropped %d", section, before - len(parsed.flags))

        if self.two_stage and parsed.flags:
            kept = []
            for f in parsed.flags:
                if f.confidence >= self._high_conf_skip:
                    kept.append(f)
                    continue
                keep, reason = self._validate_flag(f, section, text)
                if keep:
                    kept.append(f)
                else:
                    log.info("  [2stage] dropped [%s] reason=%s span=«%s»",
                             f.label, reason, f.span_text[:60])
            parsed.flags = kept

        return SectionPrediction(section=section, flags=parsed.flags)

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
