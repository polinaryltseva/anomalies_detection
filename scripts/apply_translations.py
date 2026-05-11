# -*- coding: utf-8 -*-
"""Безопасное снижение англицизмов в build_vkr.py.

Применяет замены ТОЛЬКО к содержимому Python-string-литералов, не трогая
имена функций/переменных/импортов. Использует tokenize для точного парсинга.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/build_vkr.py"


def transform_text(s: str) -> str:
    """Применяет все замены к строке текста (без кавычек-обрамления)."""

    # === Опечатки ===
    s = s.replace("custom custom fine-tuned", "пользовательская дообученная")

    # === Двухступенчатый ввод терминов в Аннотации (один раз) ===
    s = s.replace(
        "сформирован whitelist из 15",
        "сформирован whitelist (далее – белый список) из 15",
    )
    s = s.replace(
        "supervised fine-tuning доменно-специфичной",
        "supervised fine-tuning (далее – дообучение) доменно-специфичной",
    )
    s = s.replace(
        "Стоимость inference – около 15 долларов",
        "Стоимость вывода модели (inference) – около 15 долларов",
    )
    s = s.replace(
        "demonstrates demonstrated transfer learning",  # safety
        "demonstrated transfer learning",
    )
    s = s.replace(
        "демонстрирует transfer learning: распознавание 26 кондитерских",
        "демонстрирует перенос обучения (transfer learning): распознавание 26 кондитерских",
    )

    # === transfer learning ===
    s = re.sub(r"\bDemonstrated transfer learning\b", "Продемонстрированный перенос обучения", s)
    s = re.sub(r"\btransfer learning\b", "перенос обучения", s)
    s = s.replace("transfer-learning-демонстрацией", "демонстрацией переноса обучения")

    # === bid rigging ===
    s = re.sub(r"\bbid-rigging detection\b", "детекция сговоров на торгах", s)
    s = re.sub(r"\bBid rigging\b", "Сговор на торгах (bid rigging)", s, count=1)
    s = re.sub(r"\bbid rigging\b", "сговоры на торгах", s)
    s = re.sub(r"\bbid-rigging\b", "сговоров на торгах", s)

    # === whitelist ===
    s = re.sub(r"\bWhitelist W1–W15\b", "Белый список W1–W15", s)
    s = re.sub(r"\bwhitelist W1–W15\b", "белый список W1–W15", s)
    s = re.sub(r"\bWhitelist\b", "Белый список", s)
    s = re.sub(r"\bwhitelist'?[аaы]?\b", "белый список", s)
    s = re.sub(r"\bwhitelist\b", "белый список", s)
    s = re.sub(r"\bвалидатор whitelist'?[аaы]?\b", "валидатор белого списка", s)

    # === held-out ===
    s = re.sub(r"\bheld-out validation\b", "оценка на отложенной выборке", s)
    s = re.sub(r"\bheld-out данных\b", "отложенных данных", s)
    s = re.sub(r"\bheld-out лотах\b", "отложенных лотах", s)
    s = re.sub(r"\bheld-out лотов\b", "отложенных лотов", s)
    s = re.sub(r"\bheld-out лоты\b", "отложенные лоты", s)
    s = re.sub(r"\bheld-out specificity\b", "specificity на отложенной выборке", s)
    s = re.sub(r"\bheld-out корпус[аеуом]?\b", "отложенный корпус", s)
    s = re.sub(r"\bheld-out test set\b", "отложенная контрольная выборка", s)
    s = re.sub(r"\bheld-out evaluation\b", "оценка на отложенной выборке", s)
    s = re.sub(r"\bна held-out\b", "на отложенной выборке", s)
    s = re.sub(r"\bheld-out\b", "отложенный", s)

    # === lot-level / per-flag / per-label / per-section ===
    s = re.sub(r"\bLot-level (\w+)\b", r"\1 на уровне лота", s)
    s = re.sub(r"\blot-level (precision|recall|F1)\b", r"\1 на уровне лота", s)
    s = re.sub(r"\blot-level loose F1\b", "loose F1 на уровне лота", s)
    s = re.sub(r"\blot-level strict F1\b", "strict F1 на уровне лота", s)
    s = re.sub(r"\blot-level\b", "на уровне лота", s)

    s = re.sub(r"\bper-flag (precision|recall|F1)\b", r"\1 на уровне флага", s)
    s = re.sub(r"\bPer-flag (precision|recall|F1)\b", r"\1 на уровне флага", s)
    s = re.sub(r"\bper-flag\b", "на уровне флага", s)

    s = re.sub(r"\bper-label фильтр(ом|ацию|ация|ацией)?\b", r"фильтрация на уровне метки\1", s)
    s = re.sub(r"\bper-label filter\b", "фильтр на уровне метки", s)
    s = re.sub(r"\bper-label gating\b", "шлюзование по меткам", s)
    s = re.sub(r"\bper-label\b", "на уровне метки", s)

    s = re.sub(r"\bper-section gating\b", "шлюзование по разделам", s)
    s = re.sub(r"\bper-section\b", "на уровне раздела", s)

    # === stage / two-stage (НЕ трогаем "v2 + 2-stage") ===
    s = re.sub(r"\bStage 1\b", "Этап 1", s)
    s = re.sub(r"\bStage 2\b", "Этап 2", s)
    s = re.sub(r"\bStage 3\b", "Этап 3", s)
    s = re.sub(r"\bStage 4\b", "Этап 4", s)
    s = re.sub(r"\btwo-stage validation\b", "двухэтапная валидация", s)
    s = re.sub(r"\btwo-stage validator\b", "двухэтапный валидатор", s)
    s = re.sub(r"\btwo-stage\b", "двухэтапный", s)

    # === silver labels / silver TRUE ===
    s = re.sub(r"\bsilver TRUE['ыоам]*\b", "вспомогательные положительные TRUE", s)
    s = re.sub(r"\bsilver labels\b", "вспомогательная разметка", s)
    s = re.sub(r"\bsilver-метк[аио]м?\b", "вспомогательные метки", s)

    # === rule-based ===
    s = re.sub(r"\bRule-based (детектор|regex детектор)\b", r"\1 на основе правил", s)
    s = re.sub(r"\brule-based (детектор|regex детектор)\b", r"\1 на основе правил", s)
    s = re.sub(r"\brule-based pre-filter\b", "предварительный фильтр на основе правил", s)
    s = re.sub(r"\brule-based silver\b", "вспомогательная разметка на основе правил", s)
    s = re.sub(r"\bRule-based\b", "На основе правил", s)
    s = re.sub(r"\brule-based\b", "на основе правил", s)

    # === trade-off / cost-quality ===
    s = re.sub(r"\bcost-quality trade-off\b", "компромисс стоимость–качество", s)
    s = re.sub(r"\bcost-quality\b", "стоимость–качество", s)
    s = re.sub(r"\btrade-off\b", "компромисс", s)
    s = re.sub(r"\bTrade-off\b", "Компромисс", s)

    # === pretraining ===
    s = re.sub(r"\bpretraining-знани[яеи]+\b", "знание из предобучения", s)
    s = re.sub(r"\bpretraining-этапа\b", "этапа предобучения", s)
    s = re.sub(r"\bpretraining[еуа]?\b", "предобучение", s)
    s = re.sub(r"\bPretraining\b", "Предобучение", s)

    # === multi-label ===
    s = re.sub(r"\bmulti-label classification\b", "многометочная классификация", s)
    s = re.sub(r"\bmulti-label-таксономии\b", "многометочной таксономии", s)
    s = re.sub(r"\bmulti-label-таксономия\b", "многометочная таксономия", s)
    s = re.sub(r"\bmulti-label\b", "многометочный", s)

    # === frontier ===
    s = re.sub(r"\bfrontier-model\b", "передовая модель", s)
    s = re.sub(r"\bfrontier-моделью\b", "передовой моделью", s)
    s = re.sub(r"\bfrontier-модели\b", "передовой модели", s)
    s = re.sub(r"\bfrontier-альтернативы\b", "передовой альтернативы", s)
    s = re.sub(r"\bfrontier-zero-shot\b", "передовой zero-shot", s)
    s = re.sub(r"\bFrontier zero-shot\b", "Передовой zero-shot", s)
    s = re.sub(r"\bfrontier zero-shot\b", "передовой zero-shot", s)

    # === false positives (только в прозе, FALSE-код в таблицах не трогаем) ===
    s = re.sub(r"\bfalse positive[s]?\b", "ложные срабатывания", s)
    s = re.sub(r"\bfalse negative[s]?\b", "ложные пропуски", s)
    s = re.sub(r"\bFalse positive[s]?\b", "Ложные срабатывания", s)
    s = re.sub(r"\bFalse negative[s]?\b", "Ложные пропуски", s)
    s = re.sub(r"\bFP паттернов\b", "паттернов ложных срабатываний", s)
    s = re.sub(r"\bFP rate\b", "доля ложных срабатываний", s)

    # === pipeline ===
    s = re.sub(r"\bproduction cascade pipeline['аяою]*\b", "каскадная архитектура", s)
    s = re.sub(r"\bcascade pipeline'?a?\b", "каскадная архитектура", s)
    s = re.sub(r"\bcascade pipeline\b", "каскадная архитектура", s)
    s = re.sub(r"\bcascade-pipeline\b", "каскадный конвейер", s)
    s = re.sub(r"\bbaseline-pipeline'?[аое]?\b", "исходный конвейер", s)
    s = re.sub(r"\bbaseline pipeline'?[аое]?\b", "исходный конвейер", s)
    s = re.sub(r"\bpipeline'?а\b", "конвейера", s)
    s = re.sub(r"\bpipeline'?ом\b", "конвейером", s)
    s = re.sub(r"\bpipeline'?е\b", "конвейере", s)
    s = re.sub(r"\bpipeline'?у\b", "конвейеру", s)
    s = re.sub(r"\bpipeline'?ы\b", "конвейеры", s)
    s = re.sub(r"\bpipeline'?ов\b", "конвейеров", s)
    s = re.sub(r"\bpipeline'?ам\b", "конвейерам", s)
    s = re.sub(r"\bpipeline'?ах\b", "конвейерах", s)
    s = re.sub(r"\bPipeline\b", "Конвейер", s)
    s = re.sub(r"\bpipeline\b", "конвейер", s)

    # === baseline (контекстно) ===
    s = re.sub(r"\bbaseline c codebook'ом v1\b", "исходная конфигурация с codebook v1", s)
    s = re.sub(r"\bzero-shot baseline'?[аеыов]*\b", "исходные конфигурации без дообучения", s)
    s = re.sub(r"\bzero-shot baselines\b", "исходные конфигурации без дообучения", s)
    s = re.sub(r"\bbaseline'?ы\b", "исходные конфигурации", s)
    s = re.sub(r"\bbaseline'?а\b", "исходной конфигурации", s)
    s = re.sub(r"\bbaseline'?е\b", "исходной конфигурации", s)
    s = re.sub(r"\bbaseline\b", "исходная конфигурация", s)
    s = re.sub(r"\bBaseline\b", "Исходная конфигурация", s)
    # Восстанавливаем имена конфигураций
    s = s.replace("v1 исходная конфигурация", "v1 baseline")
    s = s.replace("v1 Исходная конфигурация", "v1 baseline")

    # === fine-tuning / fine-tuned ===
    s = re.sub(r"\bsupervised fine-tuning\b", "дообучение", s)
    s = re.sub(r"\bSupervised fine-tuning\b", "Дообучение", s)
    s = re.sub(r"\bFine-tuning\b", "Дообучение", s)
    s = re.sub(r"\bfine-tuning доменно\b", "дообучение доменно", s)
    s = re.sub(r"\bfine-tuning процедур[ауы]?\b", "процедура дообучения", s)
    s = re.sub(r"\bfine-tuning через OpenAI\b", "дообучение через OpenAI", s)
    s = re.sub(r"\bfine-tuning'?[аое]?\b", "дообучение", s)
    s = re.sub(r"\bfine-tuning\b", "дообучение", s)

    s = re.sub(r"\bfine-tuned модель\b", "дообученная модель", s)
    s = re.sub(r"\bfine-tuned-моделью\b", "дообученной моделью", s)
    s = re.sub(r"\bfine-tuned-модели\b", "дообученной модели", s)
    s = re.sub(r"\bfine-tuned gpt-4\.1 v3a\b", "дообученная gpt-4.1 v3a", s)
    s = re.sub(r"\bfine-tuned gpt-4\.1\b", "дообученная gpt-4.1", s)
    s = re.sub(r"\bfine-tuned-компонент\b", "дообученный компонент", s)
    s = re.sub(r"\bfine-tuned\b", "дообученный", s)
    s = re.sub(r"\bFine-tuned\b", "Дообученный", s)

    # === inference ===
    s = re.sub(r"\bInference cost\b", "Стоимость вывода", s)
    s = re.sub(r"\binference cost\b", "стоимость вывода", s)
    s = re.sub(r"\binference time\b", "время вывода", s)
    s = re.sub(r"\binference-стоимость\b", "стоимость вывода", s)
    s = re.sub(r"\binference['ам]*\b", "вывод модели", s)

    # === prompt → запрос (НЕ трогаем prompt-chaining, prompt caching, system-prompt) ===
    s = re.sub(r"\bsystem-промпт[аеуыом]*\b", "системный запрос", s)
    s = re.sub(r"\bsystem prompt\b", "системный запрос", s)
    s = re.sub(r"\bсистемного промпта\b", "системного запроса", s)
    s = re.sub(r"\bсистемный промпт\b", "системный запрос", s)
    s = re.sub(r"\bсистемном промпте\b", "системном запросе", s)
    s = re.sub(r"\bprompt engineering\b", "разработка запросов", s)
    s = re.sub(r"\bprompt-engineering\b", "разработку запросов", s)

    # === triage ===
    s = re.sub(r"\btriage-уровня\b", "уровня приоритизации", s)
    s = re.sub(r"\btriage tool\b", "инструмент приоритизации", s)
    s = re.sub(r"\btriage-tool\b", "инструмент приоритизации", s)
    s = re.sub(r"\bдля triage\b", "для приоритизации", s)
    s = re.sub(r"\btriage\b", "приоритизация", s)
    s = re.sub(r"\bTriage\b", "Приоритизация", s)

    # === workflow / output / threshold / compute / screening ===
    s = re.sub(r"\bworkflow[ам]*\b", "рабочий процесс", s)
    s = re.sub(r"\bproduction workflow\b", "производственный процесс", s)
    s = re.sub(r"\bWorkflow\b", "Рабочий процесс", s)

    s = re.sub(r"\boutputs\b", "выходы", s)
    s = re.sub(r"\bv3\+2s outputs\b", "выходы v3+2s", s)

    s = re.sub(r"\bconfidence-threshold\b", "порог уверенности confidence", s)
    s = re.sub(r"\bconfidence threshold\b", "порог уверенности confidence", s)
    s = re.sub(r"\bthreshold tuning\b", "настройка порогов", s)

    s = re.sub(r"\bcompute-бюджет[аеуоом]*\b", "вычислительный бюджет", s)
    s = re.sub(r"\bcompute-ресурс[ыов]*\b", "вычислительные ресурсы", s)

    s = re.sub(r"\bself-screening\b", "самопроверка", s)
    s = re.sub(r"\bregulatory screening\b", "регуляторная проверка", s)
    s = re.sub(r"\bregulatory-screening\b", "регуляторная проверка", s)
    s = re.sub(r"\bпотокового screening['а]?\b", "потокового скрининга", s)
    s = re.sub(r"\bscreening['аоуи]+\b", "скрининга", s)

    # === red flag / red flags (термин с переводом при первом упоминании) ===
    s = re.sub(r"\bred flags\b", "красные флаги", s)
    s = re.sub(r"\bred flag\b", "красный флаг", s)
    s = re.sub(r"\bRed flag\b", "Красный флаг", s)

    # === ensemble ===
    s = re.sub(r"\bensemble methods\b", "ансамблевые методы", s)
    s = re.sub(r"\bensemble-методы\b", "ансамблевые методы", s)
    s = re.sub(r"\bcross-pipeline ensemble\b", "ансамбль между конвейерами", s)
    s = re.sub(r"\bEnsemble v2 ∩ v3\b", "Ансамбль v2 ∩ v3", s)
    s = re.sub(r"\bensemble v2 ∩ v3\b", "ансамбль v2 ∩ v3", s)
    s = re.sub(r"\bEnsemble\b", "Ансамбль", s)
    s = re.sub(r"\bensemble\b", "ансамбль", s)

    # === training (НЕ трогаем validation loss, training jsonl) ===
    s = re.sub(r"\btraining-выборк[аеыеуи]+\b", "обучающая выборка", s)
    s = re.sub(r"\btraining-данн[ыхеихм]+\b", "обучающих данных", s)
    s = re.sub(r"\btraining set\b", "обучающая выборка", s)
    s = re.sub(r"\btraining data\b", "обучающие данные", s)
    s = re.sub(r"\btraining tokens\b", "обучающие токены", s)
    s = re.sub(r"\btraining job[ам]*\b", "задача обучения", s)

    # === manually-* ===
    s = re.sub(r"\bmanually-annotated флаг[еах]+\b", "вручную размеченных флагах", s)
    s = re.sub(r"\bmanually-annotated флаге\b", "вручную размеченном флаге", s)
    s = re.sub(r"\bmanually-annotated\b", "вручную размеченных", s)
    s = re.sub(r"\bmanually-verified\b", "вручную верифицированных", s)
    s = re.sub(r"\bmanually-clean\b", "заведомо чистых", s)

    # === bootstrap / data augmentation / preliminary / production / deployment ===
    s = re.sub(r"\bbootstrap distillation\b", "загрузочная дистилляция", s)
    s = re.sub(r"\bbootstrap'?[аеу]?\b", "начальная загрузка", s)

    s = re.sub(r"\bdata augmentation\b", "аугментация данных", s)

    s = re.sub(r"\bpreliminary\b", "предварительные", s)

    s = re.sub(r"\bProduction-стоимость\b", "Производственная стоимость", s)
    s = re.sub(r"\bproduction-стоимость\b", "производственная стоимость", s)
    s = re.sub(r"\bproduction-конфигурация\b", "производственная конфигурация", s)
    s = re.sub(r"\bproduction-конфигураци[яиейю]+\b", "производственной конфигурации", s)
    s = re.sub(r"\bproduction-выводы\b", "производственные выводы", s)
    s = re.sub(r"\bproduction-deployment[ам]?\b", "производственное развёртывание", s)
    s = re.sub(r"\bproduction-grade\b", "производственного уровня", s)
    s = re.sub(r"\bproduction-ready cascade pipeline['аи]*\b", "производственно-готовая каскадная архитектура", s)
    s = re.sub(r"\bproduction-ready\b", "производственно-готовый", s)
    s = re.sub(r"\bдля production\b", "для производства", s)
    s = re.sub(r"\bв production-сценарии\b", "в производственном сценарии", s)
    s = re.sub(r"\bв production-сценариях\b", "в производственных сценариях", s)

    s = re.sub(r"\bдеплой\b", "развёртывание", s)
    s = re.sub(r"\bдеплоя\b", "развёртывания", s)
    s = re.sub(r"\bdeployment\b", "развёртывание", s)

    # === discriminative / memorization / generalization ===
    s = re.sub(r"\bdiscriminative power\b", "дискриминативная сила", s)
    s = re.sub(r"\bdiscriminative-сигнал[аов]*\b", "разделяющий сигнал", s)
    s = re.sub(r"\bcontent-discriminative сигнала\b", "содержательно разделяющего сигнала", s)
    s = re.sub(r"\bmemorization\b", "запоминание", s)
    s = re.sub(r"\bdemonstrated generalization\b", "продемонстрированное обобщение", s)
    s = re.sub(r"\bDemonstrated generalization\b", "Продемонстрированное обобщение", s)
    s = re.sub(r"\bgeneralization\b", "обобщение", s)
    s = re.sub(r"\bGeneralization\b", "Обобщение", s)

    # === outcome-метрики ===
    s = re.sub(r"\boutcome-метрик[иам]+\b", "метрики по результатам торгов", s)
    s = re.sub(r"\boutcome-метрики\b", "метрики по результатам торгов", s)
    s = re.sub(r"\boutcome-нарушени[яеьмй]+\b", "нарушения по результатам торгов", s)
    s = re.sub(r"\boutcome-based\b", "на основе результатов торгов", s)
    s = re.sub(r"\boutcome-критериям\b", "критериям по результатам", s)
    s = re.sub(r"\boutcome-метками\b", "метками по результатам", s)

    # === text-based / brand-* ===
    s = re.sub(r"\btext-based\b", "текстовый", s)
    s = re.sub(r"\bbrand-в-ТЗ\b", "бренда в ТЗ", s)
    s = re.sub(r"\bBrand-mentions\b", "Упоминания брендов", s)
    s = re.sub(r"\bbrand-mention[sаиа]*\b", "упоминания брендов", s)
    s = re.sub(r"\bbrand-targeting\b", "нацеливание на бренд", s)
    s = re.sub(r"\bbrand-recognition\b", "распознавание брендов", s)

    # === failure modes / sweet spot ===
    s = re.sub(r"\bfailure modes\b", "режимов отказа", s)
    s = re.sub(r"\berror patterns\b", "паттерны ошибок", s)
    s = re.sub(r"\bsweet spot\b", "оптимальная точка", s)

    # === sibling ===
    s = re.sub(r"\bsibling-эксперимент\b", "парный эксперимент", s)
    s = re.sub(r"\bSibling-эксперимент\b", "Парный эксперимент", s)
    s = re.sub(r"\bsibling['аоу]?\b", "парный вариант", s)

    # === scope ===
    s = re.sub(r"\bскоуп[аеуы]?\b", "область", s)

    # === smoke-test / synthetic seed ===
    s = re.sub(r"\bsmoke-test\b", "контрольный тест", s)
    s = re.sub(r"\bSmoke-test\b", "Контрольный тест", s)
    s = re.sub(r"\bsynthetic seed\b", "синтетический набор", s)
    s = re.sub(r"\bSynthetic seed\b", "Синтетический набор", s)

    # === consumer-grade ===
    s = re.sub(r"\bconsumer-grade\b", "потребительского уровня", s)
    s = re.sub(r"\bconsumer-GPU\b", "потребительском GPU", s)
    s = re.sub(r"\bcost-эффективность\b", "соотношение стоимости и качества", s)
    s = re.sub(r"\bcost-quality профил[ьеяюм]+\b", "профиль стоимость–качество", s)

    # === long-tail / hard cases ===
    s = re.sub(r"\blong-tail\b", "редкие", s)
    s = re.sub(r"\bhard cases\b", "сложные случаи", s)
    s = re.sub(r"\bHard cases\b", "Сложные случаи", s)
    s = re.sub(r"\bhard negatives\b", "сложные отрицательные примеры", s)

    # === high-confidence / high-precision ===
    s = re.sub(r"\bhigh-confidence паттернах\b", "высокодостоверных паттернах", s)
    s = re.sub(r"\bhigh-confidence\b", "высокодостоверный", s)
    s = re.sub(r"\bhigh-precision паттерн[аыовм]+\b", "высокоточные паттерны", s)
    s = re.sub(r"\bhigh-precision\b", "высокоточный", s)
    s = re.sub(r"\bhigh-conf-сигнал[аов]*\b", "высокодостоверные сигналы", s)
    s = re.sub(r"\bhigh-conf-флаг[аиов]*\b", "высокодостоверные флаги", s)

    # === Defensive rule, Russian-origin priority, blocking, verbatim ===
    s = re.sub(r"\bDefensive rule\b", "Защитное правило", s)
    s = re.sub(r"\bdefensive rule\b", "защитное правило", s)
    s = re.sub(r"\bRussian-origin priority\b", "приоритет российского происхождения", s)
    s = re.sub(r"\bverbatim-цитат[аыеу]+\b", "дословные цитаты", s)
    s = re.sub(r"\bverbatim-ссылк[ииаеи]+\b", "дословные ссылки", s)
    s = re.sub(r"\bverbatim\b", "дословный", s)
    s = re.sub(r"\bblocking-условиями\b", "блокирующими условиями", s)
    s = re.sub(r"\bSingle annotator\b", "Единственный аннотатор", s)
    s = re.sub(r"\bsingle annotator\b", "единственный аннотатор", s)
    s = re.sub(r"\bsingle-annotator setup\b", "при единственном аннотаторе", s)

    s = re.sub(r"\bbottleneck\b", "узкое место", s)
    s = re.sub(r"\bcheck-лист[аеуыовм]+\b", "чек-лист", s)

    s = re.sub(r"\bdownstream-задачу\b", "целевую задачу", s)
    s = re.sub(r"\bdownstream task\b", "целевая задача", s)
    s = re.sub(r"\bdownsampling\b", "снижение количества", s)
    s = re.sub(r"\bdownsampled\b", "снижено количество", s)

    s = re.sub(r"\battack surface\b", "поверхность атаки", s)
    s = re.sub(r"\bопорной поверхностью атаки\b", "основной поверхностью атаки", s)

    s = re.sub(r"\bin-prompt интерпретируемост[ьюи]+\b", "интерпретируемость через системный запрос", s)
    s = re.sub(r"\bpost-hoc подход\b", "постфактумный подход", s)
    s = re.sub(r"\bpost-hoc temperature scaling\b", "постфактумное масштабирование температуры", s)
    s = re.sub(r"\bpost-hoc\b", "постфактумный", s)

    s = re.sub(r"\bself-consistency\b", "самосогласованность", s)
    s = re.sub(r"\bcross-national evaluation\b", "межстрановое сравнение", s)
    s = re.sub(r"\bcross-national\b", "межстрановой", s)
    s = re.sub(r"\btransnational\b", "межгосударственный", s)
    s = re.sub(r"\bcross-pipeline consistency\b", "согласованность между конвейерами", s)

    s = re.sub(r"\bAdversarial robustness\b", "Устойчивость к adversarial-атакам", s)
    s = re.sub(r"\badversarial robustness\b", "устойчивость к adversarial-атакам", s)

    s = re.sub(r"\bsemantic search\b", "семантический поиск", s)
    s = re.sub(r"\bre-train\b", "повторное обучение", s)
    s = re.sub(r"\bsummary-статистик[ииам]+\b", "сводные статистики", s)

    s = re.sub(r"\bspan extraction\b", "извлечение фрагмента", s)
    s = re.sub(r"\bspan-предсказани[ийяею]+\b", "предсказания фрагментов", s)
    s = re.sub(r"\bspan IoU\b", "IoU фрагмента", s)
    s = re.sub(r"\bSpan IoU\b", "IoU фрагмента", s)

    s = re.sub(r"\bbid-data\b", "числовые данные торгов", s)
    s = re.sub(r"\bbid data\b", "числовые данные торгов", s)

    s = re.sub(r"\bcache hit rate\b", "коэффициент попаданий в кэш", s)

    s = re.sub(r"\bCustom-модель\b", "Пользовательская модель", s)
    s = re.sub(r"\bcustom-модель\b", "пользовательская модель", s)
    s = re.sub(r"\bannotation guideline['аеу]?\b", "руководство по разметке", s)

    s = re.sub(r"\bbulk-прогон[аеыовам]+\b", "массовый прогон", s)
    s = re.sub(r"\bbulk-pipeline['аеыов]+\b", "массовый конвейер", s)
    s = re.sub(r"\bbulk corpus\b", "массовый корпус", s)
    s = re.sub(r"\bbulk-выборки\b", "массовой выборки", s)

    # Опечатка
    s = re.sub(r"manipulator-провер[аоеыуи]+\s+verified[\s-]?clean", "вручную проверенных чистых", s)

    return s


def main():
    src = SRC.read_text(encoding="utf-8")

    # Парсим Python через tokenize
    tokens = list(tokenize.tokenize(io.BytesIO(src.encode("utf-8")).readline))

    # Собираем заменённую версию через позиции токенов
    lines = src.splitlines(keepends=True)

    # Делаем массив: (start_offset, end_offset, replacement) для каждого STRING-токена
    edits = []
    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        # Извлекаем prefix (r, b, f) и кавычки
        m = re.match(r"^(r?b?|b?r?|f?r?|r?f?|f?b?|b?f?)?(\"\"\"|\'\'\'|\"|\')(.*)\\2$", tok.string, re.DOTALL)
        if not m:
            # Try with non-greedy quote
            for prefix in ("rb", "br", "fr", "rf", "fb", "bf", "r", "b", "f", ""):
                for quote in ("\"\"\"", "'''", "\"", "'"):
                    if tok.string.startswith(prefix + quote) and tok.string.endswith(quote):
                        content = tok.string[len(prefix) + len(quote):-len(quote)]
                        new_content = transform_text(content)
                        if new_content != content:
                            new_string = prefix + quote + new_content + quote
                            edits.append((tok.start, tok.end, new_string))
                        break
                else:
                    continue
                break
            continue
        prefix, quote, content = m.group(1) or "", m.group(2), m.group(3)
        new_content = transform_text(content)
        if new_content != content:
            new_string = prefix + quote + new_content + quote
            edits.append((tok.start, tok.end, new_string))

    # Применяем edits — от конца к началу, чтобы позиции не сдвигались
    edits.sort(key=lambda e: (e[0][0], e[0][1]), reverse=True)

    new_lines = list(lines)
    for (start_row, start_col), (end_row, end_col), repl in edits:
        # Конвертируем в 0-based
        sr = start_row - 1
        er = end_row - 1
        if sr == er:
            new_lines[sr] = new_lines[sr][:start_col] + repl + new_lines[sr][end_col:]
        else:
            # Многострочный токен (тройные кавычки)
            first = new_lines[sr][:start_col] + repl
            last = new_lines[er][end_col:]
            new_lines[sr:er+1] = [first + last]

    new_src = "".join(new_lines)
    SRC.write_text(new_src, encoding="utf-8")

    print(f"Размер до:    {len(src):>7} символов")
    print(f"Размер после: {len(new_src):>7} символов")
    print(f"Изменение:    {len(new_src) - len(src):+d} символов")
    print(f"Обработано string-токенов с заменами: {len(edits)}")


if __name__ == "__main__":
    main()
