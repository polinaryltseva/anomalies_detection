# FT v3 Plan — Production-Grade Fine-Tuned Model для 223-ФЗ

**Цель**: получить **самую сильную** fine-tuned модель в линейке через
комбинацию SFT (расширенный датасет с diverse coverage) + DPO refinement.

**Дедлайн**: 12 мая 2026.
**Бюджет**: $55-70 OpenAI API.
**Ожидаемый прирост**: precision 87.5% → 90-95%, recall 2× (8 → 15-25 флагов
на 20 held-out лотов), pattern coverage 2 → 5-6 типов.

---

## 🔑 Ключевые insights из research (best practice)

1. **DPO теперь доступен для gpt-4.1** (не только SFT).
   Direct Preference Optimization — пары (preferred, rejected). Это даёт
   +15-30% качества vs только SFT.
   Sources:
   - [OpenAI Cookbook: Choosing Between SFT, DPO, and RFT](https://cookbook.openai.com/examples/fine_tuning_direct_preference_optimization_guide)
   - [Fine-tune the GPT-4.1 family using DPO](https://community.openai.com/t/fine-tune-the-gpt-4-1-family-using-direct-preference-optimization/1285667)

2. **SFT → DPO** — стандартный production workflow:
   - SFT учит «как надо» (учиться на правильных ответах)
   - DPO учит «как НЕ надо» (различать правильное от неправильного)
   - Performing SFT before DPO establishes a robust initial policy,
     ensuring the model already prefers correct responses.

3. **Quality > Quantity**: 500 high-quality examples побеждают 1000 шумных.
   Doubling dataset → linear (not exponential) increase in model quality.

4. **Class balance критичен для recall**: model under-predicts если
   несбалансирован. FT v2 был 46% positive (vs v1's 14%) — именно поэтому
   recall вырос. FT v3 цель — 50%.

5. **Threshold tuning** на inference: лучше при инференсе принимать low-conf
   флаги если recall важнее точности.

---

## 📊 Текущее состояние (2026-05-06)

### Корпус
- **1018 lot dirs** (1461 lot_id в manifest, 1013 с файлами)
- **923 проанализированы rule_detector** (R1+R3+R5)
- **396 проанализированы v3+2stage** (старая версия, не нужно расширять)

### Existing annotations (284 total)
| Source | Count | TRUE | PARTIAL | FALSE |
|---|---|---|---|---|
| v1 manual (121-flag pack) | 121 | 8 | 8 | 105 |
| v2 manual review (held-out flags) | 74 | 3 | 8 | 63 |
| Ensemble verdicts | 7 | 2 | 1 | 4 |
| GPT-5.5 silver | 4 | 3 | 1 | 0 |
| Rule_trues (R1+R3, старая партия) | 78 | 78 | 0 | 0 |
| **TOTAL** | **284** | **94** | **18** | **172** |

### Rule detector на расширенном корпусе
- 250 флагов на 923 лотах
- 158 `brand_or_model_targeting` (R3 patterns: «не допускается эквивалент»)
- ~80 `ambiguous_evaluation_criteria` (R1 patterns: «Не предусмотрено»)
- ~12 другие (R5 единственный участник etc.)

= **~250 silver TRUE candidates** доступны (vs 78 в FT v2 training).

---

## 📋 Phased Plan (5 phases, 3-4 дня)

### Phase 1 — Расширение rule-based silver TRUE labels (15 мин, $0)

**Что**: обновить `data/labeled/rule_trues.jsonl` с новых 923 rule_detector выходов.

**Скрипт**: `scripts/extract_rule_trues.py` (уже существует, надо перезапустить).

**Ожидаем**: 78 → ~150-200 silver TRUE.

**ВАЖНО**: rule R1+R3 имеют 100% precision (manually verified ранее), поэтому
silver labels — gold-quality для training.

```bash
python scripts/extract_rule_trues.py
```

### Phase 2 — Massive manual annotation (1-2 дня, $0)

**Цель**: добавить **150 разнообразных** manually-verified flags для покрытия
паттернов где FT v2 слабо работала.

**Стратегия по таргетам:**

| Pattern | Целевое количество | Где искать |
|---|---|---|
| **brand+model в pricing БЕЗ «или эквивалент»** (Adventurer Pro-style) | 30-35 | rule_detector R3 не покрывает; искать в v1/v3+2s outputs где label=brand_or_model_targeting в section=pricing/tz |
| **Extreme contract terms** (≥120 дн оплата, односторонний отказ, ±30% объём) | 20-25 | v3+2s outputs label=unusual_contract_terms |
| **ФИО / ИНН аффилированных лиц** (COI signals) | 20-25 | v1/v3+2s outputs label=conflict_of_interest_signals |
| **Narrow tech specs** (узкие диапазоны параметров) | 20 | label=restrictive_tech_specs в section=tz |
| **Hard negatives — lookalikes which are FALSE** | 30 | где модель ошибочно флагает, как FT v2's «*-или эквивалент» FP |
| **Diverse FALSE** (стандартные нормы 223-ФЗ) | 20 | для balance |
| **TOTAL NEW** | **~150** | |

**Hard negatives критичны** — они учат модель **отличать** real anomalies от
lookalikes. Это особенно важно для DPO (где нужны preferred/rejected пары).

**Скрипты**:
1. `scripts/prepare_v3_review.py` (новый) — генерирует `v3_review_pack.md` со
   стратифицированным sample из v3+2s + rule outputs.
2. `scripts/write_v3_annotations.py` (новый) — verdict map для 150 флагов.

**Manual работа**: ~6-8 часов чтения + verdict (Claude делает).

### Phase 3 — Build training dataset (30 мин, $0)

**Что**: объединить все annotations в FT v3 datasets с правильной композицией.

**Композиция**:
- 250 silver TRUE (rule-based, 100% precision verified) — но downsample до 100
  чтобы не overfit на 2 паттерна
- 16 v1 manual TRUE
- 3 v2 manual TRUE (из v2 review)
- 2 ensemble TRUE
- 3 gpt-5.5 silver TRUE
- 18 PARTIAL (treat as low-conf TRUE, conf=0.55)
- ~100 manually-annotated NEW TRUE/PARTIAL (от Phase 2)
- **= ~242 positive examples**

- ~242 negative examples (matching count для 50/50 balance)
  - Из 172 manually-annotated FALSE (best quality)
  - + ~70 negative section examples из bottom-10 + clean lots

**= ~485 training examples** (vs FT v2: 204).

**Train/val split**: 90/10 stratified by label/verdict → 437 train + 48 val.

**Скрипт**: `scripts/build_finetune_dataset_v3.py` (новый, base on v2 version).

### Phase 4 — SFT hyperparameter sweep (1 час, $28-32)

**Что**: запустить **3 параллельных** SFT job для поиска лучшего config.

| Run | Epochs | LR | Цель |
|---|---|---|---|
| **v3a** | 5 | default (auto, 1.0×) | **control** — тот же config что FT v2; изоляция эффекта расширенного датасета |
| **v3b** | 7 | default (1.0×) | **больше эпох** — был ли FT v2 недотренирован? |
| **v3c** | 5 | 0.5× | **conservative LR** — страховка от overfit на маленьком датасете |

**Каждый**: ~$8-14 на ~437 train examples.

**Не делаем v3d (2× LR)**: aggressive LR на 580-example датасете — лотерея, обычно хуже baseline для small data.

**Selection**: best by:
1. Validation loss (low)
2. Held-out F1 на 20 контрольных лотах (high)
3. Manual verification 10 random flags (gold)

**Скрипты**:
- `scripts/start_finetune_v3a.py` / `_v3b.py` / `_v3c.py`
- `scripts/check_finetune_v3_status.py` — monitor 3 jobs

### Phase 5 — DPO refinement (1 час, $15-20)

**Что**: взять best SFT model (например v3a) и сделать DPO fine-tune на парах
(preferred, rejected).

**Источник pairs**:
1. **FT v2 errors на held-out**: где FT v2 ошибочно flagged FALSE → preferred
   = empty array, rejected = FT v2 output. **~5-10 пар**.
2. **FT v2 misses**: где FT v2 не flagged TRUE → preferred = с flag, rejected
   = empty. **~10-15 пар**.
3. **Hard negative lookalikes** (Phase 2 manual): preferred = FALSE answer,
   rejected = «выглядит как brand_targeting» wrong answer. **~15-20 пар**.

**= 30-50 preference pairs**

**Format** (OpenAI DPO):
```json
{
  "input": {"messages": [...system..., ...user...]},
  "preferred_output": [{"role": "assistant", "content": "{\"flags\": [...]}"}],
  "non_preferred_output": [{"role": "assistant", "content": "{\"flags\": [WRONG]}"}]
}
```

**Скрипты**:
- `scripts/build_dpo_pairs.py` — генератор preference pairs из ошибок
- `scripts/start_finetune_v3_dpo.py` — DPO job
- `data/finetune_v3_dpo/preferences.jsonl` — 30-50 пар

### Phase 6 — Evaluation (1-2 часа, $5)

**Что**: прогнать ВСЕ кандидаты (v3a/b/c, v3+DPO) на:
1. **20 held-out lots** (NEW — те что не в training)
2. **Bottom-10 clean lots** (specificity)
3. **Signal-10** (recall на known TRUE patterns)
4. **Дополнительные 30 random lots из новых 600** (out-of-distribution)

**Manual verification**: руками проверю каждый flag (как делали для FT v2).

**Метрики на каждый pipeline**:
- Strict precision (TRUE only) — manually verified
- Loose precision (TRUE+PARTIAL)
- Held-out specificity (% lots correctly LOW)
- Recall на known TRUE patterns
- Lot-level F1
- Per-label precision

---

## 💰 Бюджет

| Phase | Action | Time | Cost |
|---|---|---|---|
| 1 | Update rule_trues.jsonl | 15 min | $0 |
| 2 | Manual annotation 150 flags | 6-8 hrs | $0 |
| 3 | Build FT v3 dataset | 30 min | $0 |
| 4 | SFT hyperparameter sweep (3 jobs) | 1-2 hrs | $28-32 |
| 5 | DPO refinement | 1 hr | $15-20 |
| 6 | Evaluation на 60 лотах | 1-2 hrs | $5 |
| **TOTAL** | | **3-4 days** | **$48-57** |

**Compare to user budget**: текущий баланс OpenAI ~$X. Каждый отдельный API
запуск **подтверждаем явно перед началом**.

---

## 📈 Ожидаемые гейны (реалистичные)

| Метрика | FT v2 | FT v3 SFT | FT v3 SFT+DPO |
|---|---|---|---|
| Strict precision | 87.5% | 88-92% | **90-95%** |
| Recall на 20 held-out | 8 flags | 12-18 flags | **15-25 flags** |
| Lot-level F1 | 71% | 78-83% | **85-90%** |
| Specificity (clean lots LOW) | 65% | 70-75% | **75-80%** |
| Pattern coverage | 2 (R1+R3) | 4-5 | **5-7 diverse** |
| Cost / 200 lots inference | $5 | $5 | $5 |

---

## ⚠️ Риски и mitigations

| Риск | Mitigation |
|---|---|
| DPO overfit на noisy preferences | Fallback: остановиться на best SFT, не использовать DPO |
| Diminishing returns: 485 examples → +10% а не +50% | Acceptable; реализм: расширение dataset не магия |
| Rare patterns (Adventurer Pro) не поднять recall — мало examples в реальных лотах | Honestly: некоторые patterns требуют 50+ examples каждый |
| 4 parallel SFT jobs throttle на rate limit | Запускать с 1-2 минутным интервалом, не одновременно |
| OpenAI квота закончится посреди sweep | Перед каждым job явно подтверждаем у user |

---

## 🚦 Точки явного подтверждения у user

**ОБЯЗАТЕЛЬНО спрашиваю user перед**:
1. Phase 4: запуск каждого из 3 SFT jobs (~$8-14 каждый)
2. Phase 5: запуск DPO job (~$15-20)
3. Phase 6: massive evaluation runs (>30 lots × inference)

**Можно делать без спросa** ($0 операции):
- Парсинг файлов, regex, manual annotation
- Build dataset скрипты
- Anything без OpenAI/Anthropic API calls

---

## 📁 Структура файлов

```
data/
├── labeled/
│   ├── bulk_flag_annotations.jsonl          # v1 manual (121)
│   ├── v2_flag_annotations.jsonl            # v2 manual (74)
│   ├── ensemble_annotations.jsonl           # ensemble (7)
│   ├── gpt55_annotations.jsonl              # gpt-5.5 silver (4)
│   ├── rule_trues.jsonl                     # rule R1+R3 silver (250 после Phase 1)
│   ├── v3_review_pack.{json,md}             # NEW Phase 2 review pack
│   ├── v3_flag_annotations.jsonl            # NEW Phase 2 verdicts (150)
│   └── ftv2_heldout_flags.md                # FT v2 errors для DPO pairs
├── finetune_v3/
│   ├── training.jsonl                        # Phase 3 SFT data
│   ├── validation.jsonl
│   ├── job_v3a_info.json                    # Phase 4 jobs metadata
│   ├── job_v3b_info.json
│   ├── job_v3c_info.json
│   └── eval_summary.md                       # Phase 6 metrics
├── finetune_v3_dpo/
│   ├── preferences.jsonl                     # Phase 5 DPO pairs
│   └── job_dpo_info.json
└── reports/
    └── bulk_ft_v3/<lot>.json                # Phase 6 inference outputs

scripts/
├── extract_rule_trues.py                    # Phase 1 (existing)
├── prepare_v3_review.py                     # Phase 2 (NEW)
├── write_v3_annotations.py                  # Phase 2 (NEW)
├── build_finetune_dataset_v3.py             # Phase 3 (NEW)
├── start_finetune_v3a.py / _b.py / _c.py    # Phase 4 (NEW × 3)
├── check_finetune_v3_status.py              # Phase 4 (NEW)
├── build_dpo_pairs.py                       # Phase 5 (NEW)
├── start_finetune_v3_dpo.py                 # Phase 5 (NEW)
└── run_ft_v3.py                             # Phase 6 (NEW)
```

---

## 🎯 Success criteria

**Минимум** (если DPO не сработал):
- FT v3 SFT с **88%+ strict precision** на manually-verified held-out 20 lots
- **+5 flags vs FT v2** (recall growth)
- Pattern coverage **3+ типа**

**Цель**:
- FT v3 SFT+DPO с **90%+ strict precision**
- **+10 flags vs FT v2**
- Pattern coverage **5+ типов**

**Stretch goal**:
- 95% strict precision + recall 25 flags
- Production-deployable cascade architecture

---

## 📝 Honest disclaimer

Реалистичная оценка результатов:
> «FT v3 fine-tuning с расширенным datasets и DPO refinement улучшил precision
> с 87.5% до X% и recall с 8 до Y флагов на 20 held-out лотах. Однако часть
> прироста recall обусловлена rule-based silver labels (R1+R3), которые модель
> научилась хорошо репродуцировать. Diverse pattern coverage (brand+model в
> pricing, COI ФИО) требует значительно больше manually-verified examples
> чем у нас (~30 на pattern). Это направление дальнейшей работы.»

Это **честная** оценка limitations.

---

## Source links

- [OpenAI Cookbook: SFT vs DPO vs RFT](https://cookbook.openai.com/examples/fine_tuning_direct_preference_optimization_guide)
- [OpenAI Fine-tuning API](https://platform.openai.com/docs/guides/fine-tuning/)
- [Fine-Tuning LLMs on Imbalanced Data: Best Practices](https://latitude.so/blog/fine-tuning-llms-on-imbalanced-data-best-practices)
- [DPO original paper (Rafailov et al., 2023)](https://arxiv.org/abs/2305.18290)
- [GPT-4.1 family DPO availability announcement](https://community.openai.com/t/fine-tune-the-gpt-4-1-family-using-direct-preference-optimization/1285667)
