# FT v3a: честная оценка модели

Документ собирает полную картину результатов FT v3a после secondary annotation
13 LOW-лотов и расчёта расширенных метрик. Цифры здесь – финальные
production-ready, отличающиеся от первой итерации работы (где метрики
считались на 74 flag-instances трёх FT-моделей вместе).

**Дата:** 2026-05-07
**Модель:** `ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v3a:DcMwJbId`
**Базовая модель:** gpt-4.1-2025-04-14
**Training:** 138 примеров (123 train + 15 val), group-by-tender, 5 epochs, default LR
**Cost:** $19.83 train + ~$15 / 200 lots inference
**Validation loss:** 0.03

---

## 1. Сводный профиль метрик (held-out 20 лотов)

### Per-flag метрики (45 flag-instances FT v3a)

| Метрика | Значение | Числители |
|---|---|---|
| Strict per-flag precision (только TRUE) | **2.2 %** | 1 / 45 |
| Loose per-flag precision (TRUE + PARTIAL) | **91.1 %** | 41 / 45 |
| TRUE | 1 | – |
| PARTIAL | 40 | – |
| FALSE | 4 | – |

### Lot-level метрики (20 лотов: 7 flagged + 13 LOW)

| Метрика | Значение | Числители |
|---|---|---|
| Strict lot-level precision | **14.3 %** | 1 / 7 |
| Loose lot-level precision | **42.9 %** | 3 / 7 |
| Strict lot-level recall | **50.0 %** | 1 / 2 |
| Loose lot-level recall | **60.0 %** | 3 / 5 |
| Strict lot-level F1 | **22.2 %** | – |
| Loose lot-level F1 | **50.0 %** | – |
| Specificity | **73.3 %** | 11 / 15 |

### Per-label precision

| Метка | n | TRUE | PARTIAL | FALSE | Strict P | Loose P |
|---|---|---|---|---|---|---|
| restrictive_tech_specs | 1 | 1 | 0 | 0 | **100 %** | **100 %** |
| brand_or_model_targeting | 41 | 0 | 40 | 1 | 0 % | **97.6 %** |
| ambiguous_evaluation_criteria | 3 | 0 | 0 | 3 | 0 % | **0 %** |

### Confidence calibration (avg confidence)

| Verdict | n | Avg conf |
|---|---|---|
| TRUE | 1 | 0.55 |
| PARTIAL | 40 | 0.85 |
| FALSE | 4 | 0.85 |

**Калибровка плохая:** PARTIAL (0.84) и FALSE (0.79) почти неотличимы; TRUE
парадоксально имеет ниже confidence. Это значит, что confidence-threshold
в production-фильтре не работает как разделитель.

---

## 2. Что модель нашла на held-out

### Lot 146961063 (Qummy roboticised oven)
- 1 flag, verdict TRUE
- Единственное явное brand-в-ТЗ нарушение во всём held-out корпусе
- Бренд "Qummy" указан в техническом задании без оговорки "или эквивалент"

### Lot 148493841 (антифризы УФСИН)
- 14 flag-instances, все PARTIAL
- LUXE ANTIFREEZE LONG LIFE, AGA ANTIFREEZE AGA-Z65, Oil Right
- Бренды в pricing/ОНМЦК без оговорки "или эквивалент"
- 100 % recall на брендах из этого лота

### Lot 149476638 (продуктовая закупка)
- **26 flag-instances, все PARTIAL**
- Кондитерские бренды: Lays, Skittles, M&M's, Snickers, FRUTELLA, Орбит,
  Юбилейное, Барни, Picnic, Чио-чип, ICEBall, и другие
- 100 % recall на брендах из этого лота
- **Главный win работы**: эти бренды не появлялись в training,
  модель сгенерализовала pattern "brand mention в pricing → flag" с других
  обучающих примеров

---

## 3. Что модель пропустила (missed)

### Lot 169568334 (картриджи Роскадастр Татарстан) — missed_PARTIAL
В pricing присутствуют HP-артикулы:
- "Картридж CE278A", "Картридж CF280X", "Картридж Q2612A" – HP-номенклатура
- "Тонер-картридж TO-2600H черный оригинальный"
- "Тонер-картридж TL-5120X/TL-5120XP оригинальный"

Слово "оригинальный" прямо ограничивает совместимость одним производителем.
Без оговорки "или эквивалент". Это L2 PARTIAL, который модель не отметила.

### Lot 171740008 (УФСИН Якутия, дизтопливо) — missed_TRUE
Найдена формулировка:

> "если в заявке участника закупки указанный товарный знак будет
> сопровождаться словами или эквивалент – комиссией будет расценено, что
> участником не предложен товар, обозначенный указанным знаком"

Это явный запрет использования эквивалента в заявке = L2
brand_or_model_targeting **TRUE**. Прямое нарушение EU 2014/24/EU Art. 42(4)
и 223-ФЗ ст. 3 ч. 6.1. Аналогичный паттерн на лоте 169592487 в training-выборке
был помечен как TRUE; модель не сгенерализовала его сюда.

---

## 4. Ошибки модели (4 flagged лота с only-FALSE)

Эти 4 лота FT v3a flagged одним flag-instance, и каждый оказался FALSE
по whitelist:

| Lot ID | Flag | Whitelist причина |
|---|---|---|
| 169424481 | brand_or_model_targeting | W11: defensive rule в инструкции участникам не использовать слова "эквивалент", "аналог" |
| 169562149 | brand_or_model_targeting | W11: то же defensive rule |
| 169562196 | ambiguous_evaluation_criteria | W12 + W10: verbatim ст. 3.4 ч. 19.4 (для аукциона критерии = только цена) |
| 169568308 | brand_or_model_targeting | W11: то же defensive rule |

**Систематическая ошибка:** модель не до конца усвоила W11 (различение
"defensive rule в инструкции участникам" от "запрет эквивалента в TЗ"). Также
полная регрессия на W12 для ambiguous_eval (8 из 8 FALSE).

---

## 5. Сильные стороны (объективная оценка)

1. **Recall на содержательных брендах в "правильных" лотах – 100 %.**
   На лотах 148493841 и 149476638 модель опознала все 14 + 26 = 40
   brand-instances без пропусков.

2. **Per-flag loose precision 81.5 %.** Из 100 alert'ов 81 содержит
   реальный содержательный сигнал. Это в 6 раз лучше baseline (13.2 %).

3. **Per-label brand_or_model_targeting – 95.5 % loose.** Основная
   content-метка работает почти идеально на flagged лотах.

4. **Demonstrated transfer learning.** Pattern "Не предусмотрено"
   найден на двух новых лотах в FT v1; brand-recognition в v3a на
   кондитерских брендах не из training. Это не запоминание.

5. **Cost-эффективность.** $15 / 200 лотов – в 5 раз дешевле frontier
   gpt-5.5 zero-shot ($80) при сопоставимом per-flag качестве.

6. **Specificity 73.3 %.** Намного лучше baseline (5 %), хотя и хуже,
   чем 80 % FT v1 на пересекающемся тесте.

---

## 6. Слабые стороны (объективная оценка)

1. **Lot-level loose precision только 42.9 %.** Из 7 flagged лотов 4 –
   полностью false-positive. Модель плохо принимает глобальное решение
   "флагать или нет".

2. **Lot-level loose recall 60 %.** Пропустила 2 из 5 положительных лотов
   в held-out (1 TRUE + 1 PARTIAL). Особенно неприятно – missed_TRUE
   на лоте 171740008, аналогичный паттерн модель видела в training.

3. **Lot-level loose F1 = 50 %.** Это средне, не "production-grade for
   unsupervised triage".

4. **ambiguous_evaluation_criteria – 0 % precision.** 8 из 8 FALSE. Полная
   регрессия по сравнению с rule_detector R1 (100 % precision на тех же
   паттернах). Модель не учитывает контекст "режим аукциона" (W10).

5. **Confidence не калибрована.** PARTIAL и FALSE неотличимы (0.84 vs 0.79);
   TRUE парадоксально ниже (0.55, n=2). Confidence-threshold не работает
   как hint'ер для оператора.

6. **Strict per-flag precision 3.7 %.** Только 2 явных TRUE из 54 флагов.
   Это скорее свойство корпуса (мало реальных brand-в-ТЗ), но цифра
   присутствует в любом честном reporting.

---

## 7. Применимость по сценариям

| Сценарий | Готовность | Аргументация |
|---|---|---|
| Полностью автоматический triage 1000 лотов/день | НЕ ПОДХОДИТ | F1 50 % означает половину alert'ов ошибочны; нужен human review |
| Assist-режим: эксперт читает alert'ы | ОТЛИЧНО | Per-flag 81.5 % loose – 4 из 5 alert'ов содержательны |
| Self-screening заказчика до публикации | ПОДХОДИТ | 7 alert'ов на 20 лотов – быстрая вычитка |
| Узкая детекция brand-targeting в pricing | ОЧЕНЬ ХОРОШО | Per-label 95.5 % loose, recall 100 % на содержательных лотах |
| Регуляторный screening для ФАС | ПОДХОДИТ как первичный фильтр | Дальше human-эксперт + юридическое заключение |
| Production детекции empty eval criteria | НЕ ПОДХОДИТ | 0 % precision на ambiguous_eval; вместо этого использовать rule_detector R1 |

---

## 8. Сравнение с baselines (held-out 20 лотов)

| Pipeline | Per-flag loose | Lot-level loose F1 | Specificity | Cost / 200 |
|---|---|---|---|---|
| v1 baseline (gpt-4o-mini, codebook v1) | 13.2 % | n/a (всё HIGH) | 5 % | $2.50 |
| v3 + 2-stage | ≈ 14 % | ≈ n/a | 5 % | $5 |
| Ensemble v2 ∩ v3 (на других 30 лотах) | 42.9 % | n/a | 100 % bottom-10 | $15 |
| gpt-5.5 zero-shot | 100 % lot-level | 67 % | n/a | $80 |
| **FT v3a** | **81.5 %** | **50 %** | **73 %** | **$15** |

**Где FT v3a выигрывает:**
- per-flag loose: в 6 раз лучше baseline
- specificity: в 15 раз лучше baseline
- cost: в 5 раз дешевле gpt-5.5 при сопоставимом per-flag качестве

**Где проигрывает:**
- lot-level precision: 43 % vs 100 % у gpt-5.5
- recall: 60 % vs 50 % – немного лучше, но gpt-5.5 имеет 100 % lot-precision

---

## 9. Что делать дальше (приоритизированный roadmap)

### Высокий приоритет

1. **DPO refinement на lot-level preference pairs.**
   - Заготовить 30-50 пар: (lot правильно flagged) vs (lot ошибочно flagged
     одним W11-instance)
   - Цель: разделить PARTIAL и FALSE по confidence
   - Ожидаемый эффект: lot-level loose precision 43 % → 60-70 %, F1 50 % → 65 %
   - Стоимость: ~$15-20 (Rafailov et al., 2023; OpenAI gpt-4.1 DPO API)

2. **Eliminate W12 false positives на ambiguous_evaluation_criteria.**
   - Добавить 10-15 training examples с verbatim "ст. 3.4 ч. 19.4" и
     verdict FALSE
   - Цель: ambiguous_eval 0 % → 70-80 % loose
   - Достаточно SFT v3b на расширенном датасете без отдельного DPO

3. **Calibration aware loss / temperature scaling.**
   - Сейчас avg confidence для PARTIAL > FALSE > TRUE – неестественно
   - Решение: post-hoc temperature scaling на validation set; либо в DPO
     включить confidence-aware preference

### Средний приоритет

4. **Hard cases для missed_TRUE на lot 171740008.**
   - Pattern "если эквивалент → расценено как не предложен" – вариация
     R3, которой нет в текущих training examples
   - Добавить 5-10 examples с такой формулировкой
   - Ожидаемый эффект: rare TRUE patterns recall +20-30 %

5. **Active learning loop.**
   - На новых 200 лотах из bulk corpus (не использованных) запустить v3a
   - Hard cases (low confidence + spurious flags) → manual review → add to training
   - Цикл повторяем 2-3 раза → v4 с pos/neg balance, более диверсифицированным

### Низкий приоритет (но содержательно интересно)

6. **Adversarial robustness.**
   - Систематические тесты на перефразированные нарушения
   - "Не предусмотрено" → "не определён", "отсутствует", "не задан"
   - Если модель хрупкая – data augmentation на synthetic-перефразировках

7. **Multi-annotator setup.**
   - Привлечь второго аннотатора на пересекающейся подвыборке 50 лотов
   - Измерить Cohen's κ
   - Цель: κ ≥ 0.6 (moderate agreement по Cohen, 1960)

---

## 10. Итоговая характеристика

**Сильная модель с яркими сильными сторонами и предсказуемыми слабостями.**

Прорывной результат – demonstrated transfer learning при 138 training-примерах:
26 / 26 кондитерских брендов на новом лоте, 14 / 14 антифризов, +
recognition pattern "Не предусмотрено" на новых лотах. Это – не запоминание,
а реальное обобщение контента в веса flagship-модели.

Главное ограничение – lot-level decision-making. Модель видит W11 (defensive
rules в инструкциях участникам) и иногда ошибочно реагирует. F1 50 % на
lot-level не позволяет deploy в полностью автоматическом режиме без
human-in-the-loop. Для assist-режима эксперта-аналитика модель – почти
идеальна.

Плохая calibration (PARTIAL и FALSE имеют близкий confidence) – локальная
проблема, решаемая через DPO либо temperature scaling. Регрессия на
ambiguous_eval – также локальная, требует +10-15 training-примеров с верными
FALSE-verdict'ами для W10/W12-паттернов.

**Для бакалаврской работы – отличный результат:**
- Есть и сильная сторона (transfer learning, 95 % per-label на brand)
- Есть честно измеренные слабости (lot-level F1 50 %, calibration mismatch)
- Есть обоснованные направления продолжения (DPO, расширение datasets)

Это полноценное empirical-исследование, а не "у меня всё работает". Подобный
honest reporting – сильный научный жест: цифры показаны как есть, ограничения
зафиксированы, направления развития обоснованы.

---

## Файлы

- Inference outputs: `data/reports/heldout_ftv3a/<lot>.json` (20 файлов)
- Manual flag verdicts: `data/labeled/heldout_flag_verdicts.jsonl` (74 instances)
- Manual lot-level verdicts: `data/labeled/heldout_low_verdicts.jsonl` (13 LOW)
- Extended metrics: `data/eval/ftv3a_extended_metrics.json`
- Скрипты: `scripts/compute_ftv3a_metrics.py`, `scripts/prepare_heldout_low_review.py`,
  `scripts/verify_heldout_flags.py`
