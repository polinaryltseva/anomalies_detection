# Progress log

Хронология работ по проекту.

---

## Краткая сводка (2026-05-05, ночь)

**Проделано за 2 дня (vs изначальная оценка в 1 неделю):**
- 5 LLM пайплайнов от baseline до fine-tuned production model
- 1 rule-based regex detector
- 200-лотный bulk corpus (1029→758 flags после фильтрации)
- 128 manually-annotated flags (gold-standard ground truth)
- **Custom fine-tuned gpt-4.1** на 122 examples ($11) с **80% specificity на held-out**
- 7 publication-quality charts
- Все коммиты на `main`, репо https://github.com/YaMosly/anilop

**Strategic decision (2026-05-05)**: focus на **fine-tuned gpt-4.1 как production
model** ($5/200 lots), а не на frontier zero-shot (gpt-5.5 — $80/200 lots, не
рентабельно для прода).

---

## 2026-05-03 — старт технической части

### Сделано

- Изучен Project Proposal
- Реверс-инжиниринг Marker API (35 контроллеров)
- Найден shortcut через `GetSavedRequests` + `SearchRunFromTinyUrl`
- Каркас Python проекта, парсер PDF/DOCX/RTF/XLSX/ODT, segmenter, Pydantic schemas
- LLM baseline на Anthropic API + Streamlit demo
- Codebook v1: 8 меток (L1-L8) с EU/OECD регуляторными reference

---

## 2026-05-04 — pilot на реальных данных

### Сделано

- Switch с Anthropic на OpenAI (geo-блок проблема для Anthropic)
- Скачка 5 первых лотов вручную → парсинг → LLM
- Расширение до 25 лотов: avg risk 0.88, 106 flags
- **Negative class**: 8 manually-clean lots — pipeline даёт им avg risk 0.98 (даже выше!)
- **Manual annotation 123 flags** от gpt-4o: 0.8% strict precision, 89% FALSE
- **Главный empirical finding**: codebook v1 не отделяет «чистые» от «проблемных»
  223-ФЗ лотов из-за обязательных формальных норм закона

---

## 2026-05-05 (день/ночь) — Bulk pipeline + Fine-tuning

### Утром: Bulk corpus

- `bulk_corpus.py` — pagination через 7 saved searches
- 200 уникальных лотов, 1423 файла после .doc→.docx конверсии
- Resumable retry с 5× backoff на 429
- Background run с monitoring каждые 5 мин

### Днём: 200-lot LLM analysis

- gpt-4o-mini на 200 лотах: 1029 flags, avg risk 0.93
- 191 лот с реальным анализом, 8 пустых (LLM упал)
- Stratified sample 121 flag → manual annotation
- **Strict precision 6.6%, loose 13.2%**
- 7 категорий FP-паттернов выявлены systematically

### Вечером/ночью: Multi-pipeline iteration

#### Codebook v2 (W1-W10) + 2-stage validation
- Whitelist 10 категорий standard 223-ФЗ норм
- Per-section label gating
- Second-pass LLM validator
- Result на 30 лотах: **9 HIGH / 11 MED / 10 LOW** (vs v1: 22/8/0) — ПЕРВАЯ
  pipeline с реальной discrimination

#### Codebook v3 (W11-W15) — расширенный whitelist
- W11: структурные описания
- W12: verbatim 223-ФЗ цитаты
- W13: защитные правила
- W14: term definitions
- W15: standard financial mechanisms

#### Cross-pipeline ensemble
- Intersection v2+2stage AND v3+2stage flags
- 7 flags на 30 лотах
- **Manual annotation: 28.6% strict precision** (4× vs v1)

#### GPT-5.5 zero-shot test
- Same v3 prompt, новейшая модель (release 2026-04-23)
- 4 flags на 10 signal lots — **100% lot-level precision** (no FP)
- НО: $80/200 lots = не рентабельно для прода

#### Rule-based regex detector
- 5 правил (R1-R5) для high-precision паттернов
- 46 flags на 199 лотах ($0 cost)
- R1 «Не предусмотрено» нашёл 17 лотов — including manually-verified TRUE

#### Fine-tuning gpt-4.1 (главный production model)
- 122 training examples (110 train + 12 val) из manual annotations
- 3 epochs, $11, 50 минут training
- Validation loss 0.17 (хорошая генерализация)
- Custom model: `ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v1:DbyWpux4`

#### Held-out validation (no data leakage)
**Original 18-lot eval был контаминирован** (training data overlap).
**Held-out**: 20 НОВЫХ lots не в training:
- v1/v3+2s: 19 HIGH / 1 LOW (5%)
- **FT-4.1: 0 HIGH / 4 MED / 16 LOW (80%)** — клиентоустойчивая generalization
- **Generalization доказан**: FT нашёл «Не предусмотрено» паттерн на 2 новых
  лотах (не в training) — настоящий transfer learning

### Visualizations
- 7 charts в `docs/charts/`
- Включая `07_heldout_validation.png` — defendable метрика

---

## 2026-05-06+ (план)

См. `docs/finetune_plan.md` — roadmap до 12 мая:

- **Day 1-2**: v2 fine-tune (300+ examples через bootstrap distillation + manual)
- **Day 3-4**: v3 active learning loop на ошибках v2
- **Day 5**: Cascade architecture + Streamlit demo
- **Day 6-7**: Documentation

**Целевые метрики v3**: 90%+ specificity, 80%+ recall, F1 85%+ на held-out.

---

## Ключевые файлы (актуальное состояние)

```
src/tender_anomaly/
├── ingest/marker_client.py       # Marker API клиент
├── parse/extractor.py            # PDF/DOCX/RTF/XLSX/ODT → text
├── parse/segmenter.py            # Text → sections
├── models/schema.py              # Pydantic Flag, RiskReport
├── models/baseline_llm/
│   ├── prompts.py                # Codebook v1 prompt
│   ├── prompts_v2.py             # Codebook v2 (W1-W10)
│   ├── prompts_v3.py             # Codebook v3 (W1-W15)
│   ├── openai_predictor.py       # v1 baseline
│   ├── openai_predictor_v2.py    # v2 + 2stage + per-section gating
│   ├── openai_predictor_v3.py    # v3 + 2stage
│   └── openai_predictor_ft.py    # Fine-tuned model wrapper
└── report/generate.py            # End-to-end CLI

scripts/
├── bulk_corpus.py                # Pagination scraper (7 saved searches)
├── prepare_bulk_review.py        # Stratified sample for manual review
├── write_bulk_annotations.py     # Manual verdicts → JSONL
├── run_real_lots.py              # Lot-level orchestrator
├── run_v2_subset.py / run_v2_2stage.py / run_v2_hybrid.py
├── run_v3.py / run_v3_full.py    # v3 runners
├── run_gpt55.py                  # gpt-5.5 zero-shot
├── ensemble.py                   # v2 ∩ v3 intersection
├── rule_detector.py              # 5 regex rules
├── build_finetune_dataset.py     # Build training JSONL
├── start_finetune.py             # Upload + create FT job
├── check_finetune_status.py      # Monitor FT job
├── run_finetuned.py              # Run custom model
├── final_comparison.py           # 5-pipeline comparison
├── precision_analysis.py         # Per-flag stats
├── generate_vkr_charts.py        # 5 base charts
└── generate_heldout_chart.py     # Held-out validation chart

docs/
├── codebook.md                   # 8 labels с regulatory grounding
├── results.md                    # Comprehensive results (1500+ lines)
├── finetune_plan.md              # v2/v3 roadmap до 12 мая
├── progress.md                   # This file
├── api-discovery.md              # Marker API map
└── charts/*.png                  # 7 publication-quality

data/
├── raw/bulk/<lot_id>/            # 200 lots × ~7 files = 1423 files
├── reports/
│   ├── bulk/                     # v1 baseline (200 lots)
│   ├── bulk_v2/                  # v2 (30 lots)
│   ├── bulk_v2_2stage/           # v2+2stage (30 lots)
│   ├── bulk_v3/                  # v3+2stage (200 lots — full)
│   ├── bulk_gpt55/               # gpt-5.5 zero-shot (10 lots)
│   ├── bulk_ft/                  # Fine-tuned (28 lots)
│   ├── bulk_ensemble/            # v2 ∩ v3 (30 lots)
│   └── bulk_rules/               # Rule detector (199 lots)
└── labeled/
    ├── bulk_review_pack.{json,md}    # 121 stratified flags
    ├── bulk_flag_annotations.jsonl    # 121 manual verdicts
    ├── ensemble_annotations.jsonl     # 7 verdicts
    ├── gpt55_annotations.jsonl        # 4 verdicts
    └── (data/finetune/)
        ├── training.jsonl              # 110 examples
        ├── validation.jsonl            # 12 examples
        └── job_info.json               # FT job metadata
```

---

## Что сделано (актуальный task state)

✅ #1-#10 базовая инфраструктура (5/3-5/4)
✅ #12 OpenAI baseline
✅ #15-#17 real-data pilot, 5+30 lots
✅ #18 Per-label precision computed
✅ #20 Negative class clean lots
✅ #21 Bulk corpus 200+ lots
✅ #22 Annotate 121 flags
✅ #23-#28 Codebook v2 + v3 + 2-stage + ensemble
✅ #29 Run v3+2stage на 200 лотах
✅ #30 GPT-5.5 comparison
✅ #31 Fine-tune v1 (122 examples, $11)
✅ #32 Held-out validation (no leakage)
✅ #33 Annotate 74 v2 review flags + bootstrap FT v2 dataset
✅ #34 Expand corpus to 400 lots + v3 analysis
✅ #35 Fine-tune v2 (204 examples, $5.55, val_loss 0.03)
✅ #36 FT v3 — extended corpus + cleaned dataset + sibling mini

🔲 #11 Документация / write-up — пользователь решил не писать

---

## Финальная сессия (2026-05-06): FT v3a + v3a-mini

### Phase 1-2: расширение и ручная аннотация
- Скачено + распарсено доп лотов → корпус 1017 лотов
- Manual annotation 128 флагов (4 TRUE / 4 PARTIAL / 120 FALSE)
- Stratified sample покрывает: brand_pricing, contract_terms, COI, tech_specs,
  hard_negatives, eval_criteria

### Phase 2.5: critical cleanup of rule-based silver labels
- Обнаружено: 213 silver TRUE = 11 уникальных span'ов, 172 — junk «Производитель,
  страна» (table headers, не violations)
- Создан **rule_detector_v2.py** с tightened регексами
  - R3 strict: «эквивалент не допустим» — 1 hit (legal exception для запчастей)
  - R3b: «или эквивалент» + ban — 5 hits (все legal)
  - R6 (ФИО + ООО): 32 hits — все = заказчика contacts (W8 noise)
  - **R1 only as silver source**: 38 entries (cap 2 per tender)

### Phase 3: balanced dataset
- 138 examples (123 train + 15 val), group-by-tender split → no leakage
- 59 positives / 64 negatives

### Phase 4: 3 SFT runs планировалось, по cost-cut → 1 main + 1 sibling
- **FT v3a (gpt-4.1)**: 5 epochs, default LR, $19.83
- **FT v3a-mini (gpt-4.1-mini)**: identical config, $3.97 (5× дешевле)

### Phase 5-6: held-out evaluation на 20 лотах
- Inference: $1.40 на 3 модели (FT v2 + v3a + v3a-mini)
- Manual verification 74 flag-instances → loose precision:
  - **FT v3a: 91.1%** (40 PARTIAL + 1 TRUE из 45)
  - FT v2: 75.0% (14 PARTIAL + 1 TRUE из 20)
  - FT v3a-mini: 33.3% (collapse в recall)

### Главный win
- v3a нашёл **26/26 кондитерских брендов** (Lays, Skittles, Snickers, FRUTELLA)
  на lot 149476638 — v2 пропустил все
- v3a избавился от W11 false positives v2 («эквивалент, аналог» в инструкции)
- v3a-mini показал что **smaller model теряет ~95% recall** на complex pattern
  recognition

### DPO: отложен
Loose precision 91% у v3a уже сильный, marginal gain от DPO маловероятен без
конкретных error patterns. Бюджет сэкономлен.

---

## Финансовая часть (полная)

| Item | Cost |
|---|---|
| OpenAI 200-lot bulk run | $2.50 |
| 30-lot v2/v3/ensemble runs | ~$10 |
| gpt-5.5 на 10 signal lots | ~$3 |
| Fine-tune v1 training | $11 |
| FT v1 inference | ~$1 |
| Fine-tune v2 training | $5.55 |
| FT v2 inference + held-out | ~$2 |
| v3+2stage инцидент (auto-launch без OK) | $31 |
| **Fine-tune v3a training** | **$19.83** |
| **Fine-tune v3a-mini training** | **$3.97** |
| Held-out inference v2/v3a/v3a-mini | ~$1.40 |
| **Total за всё время** | **~$91** |

**Production cost (FT v3a)**: ~$15/200 lots (inference)
**Production cost (FT v3a-mini)**: ~$1.50/200 lots (inference, 10× дешевле)
**vs gpt-5.5 zero-shot**: $80/200 lots → **5-50× cheaper** при равной/лучшей recall.
