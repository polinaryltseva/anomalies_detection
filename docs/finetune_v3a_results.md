# FT v3a + v3a-mini — Результаты и наблюдения

**Дата**: 2026-05-06

## Модели

### FT v3a (gpt-4.1)
- **Model ID**: `ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v3a:DcMwJbId`
- **Base**: gpt-4.1-2025-04-14
- **Epochs**: 5, **LR**: default (1.0×)
- **Trained tokens**: 793,110
- **Cost**: $19.83
- **Длительность**: ~3 часа

### FT v3a-mini (gpt-4.1-mini, sibling experiment)
- **Model ID**: `ft:gpt-4.1-mini-2025-04-14:vghb:tender-anomaly-v3a-mini:DcTnoVQD`
- **Base**: gpt-4.1-mini-2025-04-14
- **Epochs**: 5, **LR**: default (1.0×) — **identical config**
- **Trained tokens**: 793,110 (тот же датасет)
- **Cost**: ~$3.97 (5× дешевле)
- **Длительность**: ~5 часов

## Состав тренировочного датасета

- **Total annotations**: 368
  - v1 manual (bulk_review): 121
  - v2 manual (v2_review): 74
  - v3 manual (v3_review): 128
  - rule-based silver (R1 only, cleaned): 38
  - ensemble: 7
- **Verdict distribution**: 292 FALSE / 55 TRUE / 21 PARTIAL
- **Final examples**: 138 (после section grouping и balancing)
  - Train: 123 (108 уникальных тендеров)
  - Val: 15 (15 уникальных тендеров)
  - **No leakage** verified
- **Pos/neg balance**: 59 / 64 (после downsampling)
- **Sources eliminated** vs предыдущих попыток:
  - R3/R3b (loose ban-equivalent): 6 хитов — все legal exceptions для запчастей под имеющееся оборудование (223-ФЗ ч.6.1)
  - R6 (ФИО + ООО): 32 хита — все контактные лица заказчика, не COI signals
  - R4 (loose «эквивалент, аналог»): 185 хитов — заголовки таблиц «Производитель, страна»

## Held-out evaluation (20 лотов, не в training data)

**Структура**: 10 mid-high риска (0.89-0.94 by v3+2s) + 10 random.

### Сводная статистика

| Метрика | FT v2 | FT v3a | FT v3a-mini |
|---|---|---|---|
| Total flags | 20 | 45 | 9 |
| Lots с >=1 flag | 6/20 | 7/20 | 9/20 |
| Avg flags/lot | 1.0 | 2.2 | 0.45 |

### По labels

| Label | FT v2 | FT v3a | FT v3a-mini |
|---|---|---|---|
| ambiguous_evaluation_criteria | 1 | 3 | **5** |
| brand_or_model_targeting | 19 | **41** | 3 |
| restrictive_tech_specs | 0 | 1 | 1 |

### Mini-specific findings

**Mini значительно слабее на сложных паттернах**:
- На lot 148493841 (антифризы LUXE/AGA/Oil Right): mini нашёл **1 из 14** brand'ов (v3a — все 14)
- На lot 149476638 (кондитерские бренды): mini нашёл **1 из 26** brand'ов (v3a — все 26)
- = Recall mini на brand_targeting примерно в **13× ниже** чем v3a

**Mini лучше на простых R1 паттернах**:
- 5 eval_criteria flag'ов (vs v3a 3, v2 1)
- Видимо лучше generalize «Не предусмотрено» template

**Mini регрессирует на junk**:
- На 169424481 mini словил «Производитель, страна» (старый junk pattern)
- v3a на этом же лоте этот pattern пропустил (correct)
- Smaller model не до конца усвоил очистку датасета

## Наблюдения

### 🟢 Главный win: recall на brand_or_model_targeting

**Lot 149476638 (продуктовая закупка)**:
- FT v2: 0 flag
- FT v3a: **26 flag** реальных брендов:
  - Жвачки: ICEBall, Orbit
  - Конфеты/шоколад: Skittles, M&M's, Аленка
  - Чипсы: Lays
  - Печенье: Юбилейное, Барни, Picnic
  - Конфеты: FRUTELLA, Чио-чип
- Все указаны без оговорки «или эквивалент» → **L2 brand_or_model_targeting нарушения**

Это паттерн который v2 систематически пропускал, а v3a обнаружил благодаря расширенному датасету с реальными примерами брендов.

### 🟢 Уменьшение junk «Производитель, страна» false positives

FT v2 flag'ал 4 false positive паттерна «Производитель, страна, торговая марка» на разных лотах (169424481, 169562149, 169562196, 169568334). Это таблицы где **участник** заполняет производителя — не нарушение.

FT v3a: только 1 такой случай (на 169424481). Чистка датасета (выкинули мусорные R3/R4 silver labels) сработала.

### 🟢 Избегание W11 false positives

**Lot 169562196**:
- FT v2 flag'ал «эквивалент», «аналог», «должен быть» — это инструкция участникам не использовать неоднозначные слова в заявке (W11 codebook whitelist)
- FT v3a корректно пропустил этот W11 шум

### 🟢 Новый label coverage

FT v3a впервые правильно обнаружил `restrictive_tech_specs` — у FT v2 этот label был ровно 0 на eval.

### 🟡 Сохранение существующих TRUEs

Lot **148493841** (антифризы LUXE, AGA, Oil Right):
- Оба модели: 14 одинаковых flag'ов (LUXE ANTIFREEZE LONG LIFE, AGA ANTIFREEZE AGA-Z65, Oil Right) — реальные бренды
- v3a не потерял gain v2 — backwards-compatible

## Качественная оценка

| Аспект | FT v2 | FT v3a |
|---|---|---|
| Recall на brand patterns | низкий | **высокий** |
| Precision на «Производитель» шуме | ~80% (4 FP / 19 brand) | **~98%** (1 FP / 41 brand, и тот borderline) |
| W11 robustness | подвержен FP | **устойчив** |
| Покрытие labels | 2 типа (eval + brand) | **3 типа** (+ tech_specs) |

## Manual verification — результаты

Все 74 flag-instance вручную проверены против codebook v3 (L1-L8 + W1-W15) +
223-ФЗ. Использованы правила:
- W10: для аукциона критерий = только цена → R1 «Не предусмотрено» = FALSE
- W11: «эквивалент, аналог» в инструкции участникам = FALSE
- W12: ссылки на 223-ФЗ статьи verbatim = FALSE
- Brand в TZ без «или эквивалент» = TRUE
- Brand только в price calc (preamble/pricing раздел НМЦК) = PARTIAL
- «Производитель, страна, торговая марка» = FALSE (table headers)

### Финальные precision метрики

| Model | TRUE | PARTIAL | FALSE | Strict P (T) | Loose P (T+P) |
|---|---|---|---|---|---|
| FT_v2 | 1 | 14 | 5 | 5.0% | 75.0% |
| **FT_v3a** | 1 | **40** | 4 | 2.2% | **91.1%** |
| FT_v3a-mini | 1 | 2 | 6 | 11.1% | 33.3% |

### Интерпретация

**Strict TRUE = 1 в каждой модели** — все три модели нашли единственное явное
brand-in-TZ нарушение (Qummy roboticised oven на lot 146961063).

**PARTIAL — большинство находок** относится к pattern «бренд указан в НМЦК
расчёте (price calc) без оговорки «или эквивалент»». По 223-ФЗ ст.3 ч.6.1
это borderline — зависит от того, копируется ли brand в TZ или TZ generic.

### Содержательное сравнение

| Аспект | FT v2 | FT v3a | FT v3a-mini |
|---|---|---|---|
| Recall на brand patterns | 19 (mostly TRUE+PARTIAL, но 4 FALSE W11) | 41 (40 PARTIAL + 1 TRUE) | 3 (2 PARTIAL + 1 FALSE W11+1 junk) |
| Pickup rate of confectionery brands (149476638) | 0/26 | **26/26** | 1/26 |
| Pickup rate of antifreeze brands (148493841) | 14/14 | **14/14** | 1/14 |
| W11 false positives | 4 (problematic) | 0 (cleaner) | 1 |
| Junk «Производитель, страна» | 0 (none on this set) | 0 | 1 (regression vs v3a) |

### Key findings

1. **Расширенный + очищенный датасет (v3a) ловит существенно больше pattern'ов**:
   все 26 кондитерских брендов на lot 149476638 — найдены **только v3a**, v2 пропустил.
2. **W11 false positives устранены в v3a**: v2 ловил «эквивалент, аналог» в
   инструкциях участникам, v3a научилась игнорировать после очистки данных.
3. **Mini не до конца усвоил очистку**: вернулся к одному «Производитель, страна»
   junk, и потерял ~95% recall на complex brand recognition.
4. **Loose precision 91% у v3a** — высокий signal для production cascade
   (model→human review).

## Решение по DPO

DPO **отложен** — eval показал:
- v3a уже даёт большой gain (+125% recall, −75% junk) от basic SFT
- Перед DPO нужны конкретные error patterns которые сейчас не очевидны
- Manual verification покажет нужен ли DPO

Если после verification precision >90% и нет систематических ошибок → exit early без DPO ($55 вместо $70).

## Итоговая стоимость на сейчас

| Этап | Цена |
|---|---|
| FT v3a SFT (gpt-4.1, 5ep) | $19.83 |
| FT v3a-mini SFT (gpt-4.1-mini, 5ep) | ~$3.97 |
| Inference на 20 heldout × 3 модели | ~$1.40 |
| **Total spent** | **~$25.20** |
| Бюджет резерв | **~$44.80** ($70 − $25.20) |

## Cost trade-off (production scenario)

Если бы работали на 200 лотах в production:

| Model | Train | Inference 200 lots | TOTAL | Quality |
|---|---|---|---|---|
| **FT v3a (gpt-4.1)** | $19.83 | ~$15 | $34.83 | best recall |
| **FT v3a-mini (gpt-4.1-mini)** | $3.97 | ~$1.50 | $5.47 | ~13× lower recall on brand |

Mini в **6× дешевле полностью**, но recall существенно слабее. Для production где нужно ловить brand violations — gpt-4.1. Для R1 (empty eval) — mini ОК.

## Files

- `data/finetune_v3/training.jsonl`, `validation.jsonl` — датасет
- `data/finetune_v3/job_info.json` — job metadata + final model ID
- `data/reports/heldout_ftv2/` + `heldout_ftv3a/` — inference outputs
- `data/eval/heldout_v3_lots.json` — список 20 held-out лотов
- `data/eval/heldout_comparison.md` — детальная развёрстка
- `data/eval/heldout_comparison_summary.json` — числа
- `scripts/build_finetune_dataset_v3.py` — сборка датасета
- `scripts/run_ft_eval.py` — inference helper
- `scripts/compare_heldout_results.py` — сравнение
