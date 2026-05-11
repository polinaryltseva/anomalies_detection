# Production-ready Fine-tuning Plan: gpt-4.1 как final model

**Цель**: получить **дешёвую production-ready модель** для детекции аномалий в
223-ФЗ, через **iterative supervised fine-tuning** на manually-annotated данных.

**Stratregic decision (2026-05-05)**: фокусируемся на **fine-tuned gpt-4.1**,
а не на frontier zero-shot моделях:

- gpt-5.5 zero-shot достигает 100% precision, но стоит **$80 / 200 лотов**
  → нерентабельно для production
- Fine-tuned gpt-4.1 — **$3-5 / 200 лотов** inference + одноразовая тренировка
  → реалистично для прода в 1000-10000 лотов/день
- **Knowledge transfer демонстрирован**: модель сгенерализовала «Не предусмотрено»
  паттерн на новые данные

---

## Roadmap до 12 мая (8 дней)

### Сделано (v1, 2026-05-05)

✅ **Fine-tune v1**: 122 examples (110 train + 12 val), gpt-4.1, 3 epochs, $11
- Validation loss: 0.17 (хорошая генерализация)
- Held-out specificity: 80% (16/20 LOW на новых лотах)
- Recall: 62.5% на signal subset
- Demonstrated transfer: «Не предусмотрено» паттерн на 2 новых лотах

### Слабые места v1

1. **Class imbalance**: 86% FALSE / 14% TRUE+PARTIAL → модель учит «default to empty»
2. **Sparse pattern coverage**: только 8 TRUE флагов на 122 примера → каждый
   тип аномалии имеет 1-2 example → плохой recall на тонких patterns
   (Adventurer Pro, ТЕХНОПЛЕКС)
3. **No active learning**: модель не учится на своих ошибках

---

### Plan v2 (Day 1-2, 2026-05-06)

**Цель**: расширить training set до **300+ examples** с балансом 50/50.

#### Task 2.1: Bootstrap distillation через gpt-5.5 (3 часа, $10)

Использовать gpt-5.5 (100% precision на signal subset) как **teacher** для
silver labels:

1. **Empty evaluation criteria pattern**: rule detector R1 нашёл 17 лотов с
   «Не предусмотрено» / «Не применяется». Запустить gpt-5.5 на этих 17 лотах,
   взять только high-conf outputs (≥0.85) → ~12-15 silver TRUE examples.

2. **Brand targeting pattern**: v3+2stage flagged ~50 лотов с
   `brand_or_model_targeting`. Запустить gpt-5.5 на этих лотах,
   filter to confirmed brands without «или эквивалент» → ~15-25 silver TRUE.

3. **Verbatim contract terms**: v3+2stage flagged ~30 лотов с
   `unusual_contract_terms`. gpt-5.5 confirms which are real (180-day payment,
   one-sided refusal etc.) → ~10-15 silver TRUE.

= **+30-50 high-quality TRUE examples** через ~$10-15 gpt-5.5 inference.

#### Task 2.2: Manual annotation push (3-4 часа, $0)

Размечу руками **30 лотов** из v3 200-lot run (фокус на medium-risk lots с
интересными flags). Это даст:
- 20-30 verified TRUE/PARTIAL (диверсифицированные label types)
- 10+ verified FALSE (подкрепить whitelist patterns)

#### Task 2.3: Re-build dataset (1 час, $0)

```
v2 dataset:
- 60 verified TRUE (5x v1)
- 30 PARTIAL (3x v1)
- 80 FALSE (downsampled from 105, kept diverse)
= 170 examples, 35% positive class
```

Plus augmentation:
- Same anomaly with different surrounding context → force pattern learning
- Token-level span_text variations
= ~30 augmented examples → **200 total examples**

#### Task 2.4: Fine-tune v2 + ablations (2 часа, $30-50)

Запустить **3 параллельных fine-tune** на разных subsets/configs:

| Run | Data | Epochs | Cost |
|---|---|---|---|
| **v2-balanced** | 200 examples 50/50 | 5 | $15 |
| **v2-only-true** | 60 TRUE only (anchored) | 10 | $10 |
| **v2-aggressive** | 200 + class weights | 5 | $20 |

Best run выбирается по held-out F1.

---

### Plan v3 (Day 3-4, 2026-05-07/08)

**Цель**: **active learning loop** на основе ошибок v2.

#### Task 3.1: Identify v2 errors на held-out (1 час)

Сравниваем v2 outputs с rule_detector + manual baseline:
- **False negatives**: lots где FT clean, но rules или manual flagged
- **False positives**: lots где FT flagged, но manual confirmed clean

→ ~10-15 hard cases.

#### Task 3.2: Manual review hard cases + add to training (3 часа)

Размечаю 15 hard cases. Если FT v2 systematically wrong → добавляю в training.

#### Task 3.3: Fine-tune v3 (1 час, $20)

v3 dataset = v2 + 15 hard cases + variations
= **215 examples**, focused on adversarial.

Целевые метрики **v3**:
- **Held-out specificity: 90%+** (vs v1: 80%)
- **Held-out recall: 80%+** (vs v1: 62.5%)
- **F1: 85%+**

---

### Plan v4 (Day 5, 2026-05-09): Cascade & Production

#### Task 4.1: Cascade evaluation на ALL 200 лотах

```
Document
  ↓
[Stage 1] Rule detector R1-R5 ($0)
  ↓ if matches → high-confidence flag, skip ML
  ↓ else
[Stage 2] FT gpt-4.1 v3 ($5/200 lots)
  ↓ if flags → human review
  ↓ if clean → mark LOW
[Stage 3 (optional)] gpt-5.5 final validation only on flagged ($1-2 per lot)
```

**Expected output**: ~30-50 lots flagged from 200, vs v1's 200/200 HIGH.
**Cost per lot**: ~$0.05 average (rule_detector free, FT cheap).
**Human review burden**: 30-50 лотов с 1-3 флагов = 30 мин work.

#### Task 4.2: Deploy demo (4 часа)

Streamlit app с:
- Upload lot документации
- Вызов cascade pipeline
- Display flags + risk score + reasoning
- Production: live demo

---

### Plan Day 6-7 (2026-05-10/11): Documentation

- Финальное обновление results.md
- 8-10 charts (already has 7) — добавить ablation comparison v1/v2/v3
- Code review всех scripts, README

### Day 8 (2026-05-12): Buffer / final polish

---

## Technical Details

### Training data format (OpenAI Chat Completions FT)

```json
{
  "messages": [
    {"role": "system", "content": "<short prompt — codebook v3 in weights>"},
    {"role": "user", "content": "Tender ID: X\nSection: Y\n\nТекст: ..."},
    {"role": "assistant", "content": "{\"flags\": [...]}"}
  ]
}
```

### Hyperparameter sweeps for v2

| Param | v1 (current) | v2 candidate values |
|---|---|---|
| Epochs | 3 | 3, 5, 7 |
| LR multiplier | default | default, 2x, 0.5x |
| Batch size | auto | auto, 8 (если поддерживается) |
| Seed | default | 42, 100, 1337 (для статистики) |

Best config выбирается по validation loss + held-out F1.

### Data composition strategy

**Anti-overfitting на pattern types**:
- Каждый pattern должен иметь ≥5 examples (sparse → robust)
- Diversify lot domains: pharmaceuticals, construction, IT, food, transport
- Different sections: tz, pricing, requirements, evaluation, contract, procedure

**Negative class balance**:
- Don't overuse bottom-10 (too clean) — model would learn "if simple, clean"
- Include "deceptively normal" lots that have subtle issues
- Match section distribution in positive class

---

## Cost & Time Budget

| Phase | Time | Cost |
|---|---|---|
| Day 1-2: v2 prep + train | 8h | $50 |
| Day 3-4: v3 active learning | 4h | $20 |
| Day 5: Cascade + demo | 6h | $5 |
| Day 6-7: Docs + slides | 6h | $0 |
| **Total** | **24h** | **$75** |

vs initial budget: $40 estimated → $75 (more comprehensive ablation).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Bootstrap distillation добавляет gpt-5.5 errors | Filter to conf ≥0.85, manual spot-check 20% |
| Model overfits на augmented examples | Hold-out larger validation (15-20%) |
| Class imbalance не лечится 50/50 | Try class weights, focal loss-like via repeats |
| Recall на rare patterns остаётся низким | Discussion: «требуется 500+ examples per pattern» |
| Training cost превышает budget | Stop при validation plateau, use cheapest gpt-4.1-mini для ablations |

---

## Expected final state

**Empirical contribution:**
1. **5 LLM пайплайнов** + 1 rule-based + ensemble (8 точек на frontier curve)
2. **3 fine-tune iterations** (v1→v2→v3) — methodological progression
3. **Held-out validation** на 20+ untrained lots — honest metrics
4. **Cascade architecture** — production-ready system
5. **State-of-the-art** для 223-ФЗ задачи: 90%+ specificity, 80%+ recall, $5/200 lots

**Methodological contribution:**
1. **W1-W15 whitelist** — 15 категорий FP паттернов в 223-ФЗ
2. **Iterative codebook engineering** (v1→v2→v3) с validated improvement
3. **Active learning loop** — train on errors → improve
4. **Bootstrap distillation** — leverage frontier model для silver labels

**Practical contribution:**
1. **Working production model** ($5/200 lots vs $80 gpt-5.5)
2. **Streamlit demo** для defense
3. **Cascade pipeline** with regex + ML + (optional) frontier validation
4. **128+ manual annotations** as gold-standard reference dataset
