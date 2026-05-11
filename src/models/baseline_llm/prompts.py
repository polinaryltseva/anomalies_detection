"""Промпт-конструктор для LLM-baseline. Системный промпт большой и стабильный
(codebook ~8К токенов) — кэшируется через cache_control."""

from __future__ import annotations

from pathlib import Path

from tender_anomaly.config import DOCS_DIR
from tender_anomaly.models.schema import LABELS

CODEBOOK_PATH = DOCS_DIR / "codebook.md"


SYSTEM_HEADER = """Ты — независимый эксперт по комплаенсу в сфере коммерческих закупок (223-ФЗ).
Задача: прочитать фрагмент тендерной документации и определить, содержит ли он признаки
ограничения конкуренции по таксономии из приведённого ниже codebook.

ВАЖНЫЕ ПРАВИЛА:
1. Возвращай только структурированный JSON по предоставленной схеме.
2. Каждый flag должен ссылаться на ДОСЛОВНЫЙ фрагмент текста (поле `span_text`) —
   не перефразируй, не резюмируй. Цитата должна быть найдена в исходном тексте поиском.
3. Не добавляй ничего, чего нет в тексте. Если признаков нет — возвращай пустой массив flags.
4. Уверенность (`confidence`) калибруй честно: 0.9+ только когда признак очевиден;
   0.5-0.7 — есть, но допустимы трактовки; <0.5 — лучше не репортить.
5. `regulatory_reference` обязателен. Используй точные ссылки из codebook.
6. Не репортить outcome-метрики (количество участников, динамика цены) — только
   текстовые признаки в самой документации.

ТАКСОНОМИЯ МЕТОК (8 шт.):
""" + "\n".join(f"- {lbl}" for lbl in LABELS) + """

Полный codebook со всеми определениями, регуляторными ссылками и примерами:

"""


FEW_SHOT_EXAMPLES = """

ПРИМЕРЫ:

Пример 1 — секция tz содержит brand targeting + restrictive specs:
INPUT (section=tz):
  "Поставка ноутбуков Apple MacBook Pro M3 14 дюймов, оперативная память 32 ГБ,
   SSD 1 ТБ, экран с разрешением 3024×1964. Эквивалент допускается только при
   полном соответствии всем характеристикам."
OUTPUT:
  {
    "flags": [
      {
        "label": "brand_or_model_targeting",
        "section": "tz",
        "span_text": "Поставка ноутбуков Apple MacBook Pro M3 14 дюймов",
        "confidence": 0.95,
        "rationale": "Прямое указание производителя и модели; формальная оговорка 'или эквивалент' нейтрализована требованием полного соответствия.",
        "regulatory_reference": "EU Directive 2014/24/EU Art. 42(4); 223-ФЗ ст. 3 ч. 6.1"
      },
      {
        "label": "restrictive_tech_specs",
        "section": "tz",
        "span_text": "разрешением 3024×1964",
        "confidence": 0.85,
        "rationale": "Точные пиксельные характеристики характерны только для одной конкретной модели (MacBook Pro 14\\\" M3).",
        "regulatory_reference": "EU Directive 2014/24/EU Art. 42(2)"
      }
    ]
  }

Пример 2 — секция evaluation содержит ambiguous criteria:
INPUT (section=evaluation):
  "Качественная характеристика оценивается комиссией на основании
   профессионального суждения членов комиссии (0-50 баллов)."
OUTPUT:
  {
    "flags": [
      {
        "label": "ambiguous_evaluation_criteria",
        "section": "evaluation",
        "span_text": "оценивается комиссией на основании профессионального суждения членов комиссии",
        "confidence": 0.9,
        "rationale": "Критерий не содержит измеримых показателей или шкалы — оценка полностью на дискреции комиссии.",
        "regulatory_reference": "EU Directive 2014/24/EU Art. 67(4)"
      }
    ]
  }

Пример 3 — обычная секция без нарушений:
INPUT (section=tz):
  "Поставка офисной бумаги формата А4, плотность 70-100 г/м², белизна не менее 90%."
OUTPUT:
  {
    "flags": []
  }
"""


def load_codebook() -> str:
    if not CODEBOOK_PATH.exists():
        raise FileNotFoundError(f"Codebook не найден: {CODEBOOK_PATH}")
    return CODEBOOK_PATH.read_text(encoding="utf-8")


def build_system_text() -> str:
    """Полный системный промпт одной строкой — переиспользуется обоими провайдерами."""
    return SYSTEM_HEADER + load_codebook() + FEW_SHOT_EXAMPLES


def build_system_blocks() -> list[dict]:
    """Системный промпт для Anthropic API: один блок с cache_control.
    Кэш срабатывает на ≥4096 токенов префикса (на codebook_v1 ≈4–5К рус. токенов)."""
    return [
        {
            "type": "text",
            "text": build_system_text(),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def build_user_message(tender_id: str, section: str, text: str) -> str:
    """Пользовательский турн — короткий и переменный, идёт ПОСЛЕ кэша."""
    text = text[:6000]  # safety cap, типичная секция короче
    return (
        f"Tender ID: {tender_id}\n"
        f"Section: {section}\n\n"
        f"Текст секции:\n---\n{text}\n---\n\n"
        f"Найди все признаки ограничения конкуренции по codebook v1.0. "
        f"Верни строго в формате JSON по схеме."
    )
