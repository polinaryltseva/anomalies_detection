"""Сегментация полного текста тендера на смысловые разделы.

Эвристики на регулярках по якорным заголовкам. Возвращает dict {section_name: text}.
Если ни один якорь не найден, текст уходит в section "unsegmented".

Секции (RU):
  tz                  — техническое задание / описание объекта закупки
  evaluation          — критерии и порядок оценки заявок
  requirements        — требования к участникам / квалификация
  contract            — проект договора / существенные условия
  procedure           — порядок и сроки подачи заявок
  pricing             — обоснование НМЦК / пояснения по цене
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ANCHORS: dict[str, list[str]] = {
    "tz": [
        r"техническ\w+\s+задани\w+",
        r"описани\w+\s+объект\w+\s+закупк\w+",
        r"технические\s+характеристик\w+",
        r"спецификаци\w+",
    ],
    "evaluation": [
        r"критери\w+\s+(и\s+порядок\s+)?оценк\w+",
        r"порядок\s+оценк\w+",
        r"оценка\s+заявок",
        r"методика\s+оценк\w+",
    ],
    "requirements": [
        r"требовани\w+\s+к\s+участник\w+",
        r"требования\s+к\s+поставщик\w+",
        r"квалификационн\w+\s+требовани\w+",
        r"единые\s+требования\s+к\s+участник\w+",
    ],
    "contract": [
        r"проект\s+договор\w+",
        r"существенные\s+услови\w+",
        r"проект\s+контракт\w+",
        r"условия\s+договор\w+",
    ],
    "procedure": [
        r"порядок\s+(и\s+сроки\s+)?подачи\s+заявок",
        r"место,\s+дата\s+и\s+время\s+подачи",
        r"срок\s+подачи\s+заявок",
    ],
    "pricing": [
        r"обоснование\s+(нмцк|начальн\w+\s+\(?максимальн\w+\)?\s+цен\w+)",
        r"начальн\w+\s+\(?максимальн\w+\)?\s+цен\w+\s+контракт",
    ],
}


@dataclass
class Section:
    name: str
    text: str
    start: int
    end: int


_COMPILED = {
    name: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
    for name, patterns in ANCHORS.items()
}


def find_anchors(text: str) -> list[tuple[int, str]]:
    """Возвращает [(offset, section_name), ...] отсортированный по offset, без перекрытий."""
    hits: list[tuple[int, str]] = []
    for name, patterns in _COMPILED.items():
        for p in patterns:
            for m in p.finditer(text):
                hits.append((m.start(), name))
    hits.sort()
    # Дедуп по offset (берём первое попадание)
    seen: set[int] = set()
    out: list[tuple[int, str]] = []
    for off, name in hits:
        if off in seen:
            continue
        seen.add(off)
        out.append((off, name))
    return out


def segment(text: str) -> list[Section]:
    """Делит текст по якорям. Если якорей нет — одна секция unsegmented."""
    anchors = find_anchors(text)
    if not anchors:
        return [Section(name="unsegmented", text=text, start=0, end=len(text))]

    sections: list[Section] = []
    # Преамбула до первого якоря
    if anchors[0][0] > 0:
        head = text[: anchors[0][0]].strip()
        if len(head) > 100:
            sections.append(Section(name="preamble", text=head, start=0, end=anchors[0][0]))

    for i, (off, name) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(text)
        chunk = text[off:end].strip()
        if chunk:
            sections.append(Section(name=name, text=chunk, start=off, end=end))
    return sections


def merge_sections(sections: list[Section]) -> dict[str, str]:
    """Объединяет несколько кусков одной секции (если якорь встречается > 1 раза)."""
    merged: dict[str, list[str]] = {}
    for s in sections:
        merged.setdefault(s.name, []).append(s.text)
    return {k: "\n\n".join(v) for k, v in merged.items()}
