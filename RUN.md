# Как запустить пайплайн

Все шаги выполняются **с твоей машины из России** (доступ к `zakupki.gov.ru`).

## 0. Установка

```powershell
cd C:\Users\Marks\Polina

# Виртуальное окружение
python -m venv .venv
.venv\Scripts\Activate.ps1

# Зависимости
pip install -e ".[dev]"
pip install streamlit  # для демо
```

Опционально для fine-tuning (медленно, требует GPU): `pip install -e ".[finetune]"`.

## 1. Креды (`.env`)

Файл уже создан. Если кука Маркера протухла — обновить:
1. Открыть `analytics.marker-zakupki.ru/Home` в Chrome.
2. F12 → Application → Cookies → значение `SmTicketCookie`.
3. Положить в `.env` под ключом `MARKER_SESSION_TICKET=...`.

Добавить ключ LLM. По умолчанию используется **OpenAI** (`LLM_PROVIDER=openai`):

```
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
LLM_PROVIDER=openai
```

Альтернатива — Anthropic (Claude):
```
ANTHROPIC_API_KEY=sk-ant-api...
ANTHROPIC_MODEL=claude-opus-4-7
LLM_PROVIDER=anthropic
```

Дешёвые варианты для черновых прогонов: `gpt-4o-mini` (≈ $0.001/документ) или
`claude-sonnet-4-6` (в 5 раз дешевле Opus).

Любой провайдер можно ad-hoc переопределить флагом `--provider` в CLI, не меняя `.env`.

## 2. Скачать корпус

Сначала small-проба на 30 лотов нарушений 223-ФЗ (используется сохранённый поиск).

```powershell
python -m tender_anomaly.ingest.build_corpus `
  --tiny-url 3DAB2A3A9C55932EB82D3F4D088E5D2264D6B950 `
  --kind violations `
  --max-lots 30
```

Что произойдёт:
- API запрос в Маркер → список 50 лотов с нарушениями.
- Для каждого лота: `GetLotEntity` → метаданные + URL вложений.
- Скачивание каждого вложения с `zakupki.gov.ru` в `data/raw/violations/<lot_id>/`.
- Манифест в `data/raw/violations/manifest.jsonl`.

⏱ Время: ~10–15 мин на 30 лотов (по 7–8 файлов на лот, итого ~230 файлов).

Если хочется обычные закупки (а не только нарушения):
```powershell
python -m tender_anomaly.ingest.build_corpus `
  --tiny-url A9CE69C80DAAE205FFC91C4687FB6258C8C696A2 `
  --kind purchases --max-lots 30
```

## 3. Прогон LLM-baseline на пробе

```powershell
python -m tender_anomaly.report.generate `
  --manifest data/raw/violations/manifest.jsonl `
  --out data/reports/baseline_openai `
  --max-lots 10 `
  --provider openai --model gpt-4o
```

Для сравнения двух провайдеров:
```powershell
python -m tender_anomaly.report.generate --manifest data/raw/violations/manifest.jsonl `
  --out data/reports/baseline_openai --max-lots 10 --provider openai --model gpt-4o-mini
python -m tender_anomaly.report.generate --manifest data/raw/violations/manifest.jsonl `
  --out data/reports/baseline_anthropic --max-lots 10 --provider anthropic --model claude-sonnet-4-6
```

Что произойдёт:
- Для каждого из 10 лотов:
  - Парсятся все скачанные файлы (PDF / DOCX / RTF) в чистый текст.
  - Текст сегментируется на разделы (TZ, требования, критерии, договор).
  - Каждая секция → один вызов Claude с промптом из `docs/codebook.md`.
  - Возвращается `[{label, span_text, confidence, rationale, regulatory_reference}]`.
- Каждый risk report пишется в `data/reports/baseline_v1/<lot_id>.json`.
- Сводка — в `_summary.json`.

⏱ Время: ~5–10 мин на 10 лотов. Стоимость: ~$0.10–0.50 (с prompt caching после первого вызова — копейки).

## 4. Ручная разметка gold set (узкое место)

Открыть `data/reports/baseline_v1/_summary.json` и посмотреть, какие лоты модель пометила как high-risk. Открыть несколько таких лотов и проверить вручную:

- Файлы лежат в `data/raw/violations/<lot_id>/`.
- Открыть в Word/Excel/Acrobat.
- Отдельно записать «правильные» метки по `docs/codebook.md` в `data/labeled/gold.jsonl`:

```jsonl
{"lot_id": 169412087, "flags": [{"label": "brand_or_model_targeting", "section": "tz", "span_text": "Apple MacBook", "confidence": 1.0, "rationale": "exact brand", "regulatory_reference": "Art. 42(4)"}]}
```

Цель — 30–50 размеченных лотов вручную. Это test set для оценки baseline.

## 5. Метрики

Когда есть и predictions, и gold:

```powershell
python -c "
import sys, json; sys.path.insert(0, 'src')
from pathlib import Path
from tender_anomaly.eval.metrics import evaluate, risk_ranking_auc
from tender_anomaly.models.schema import Flag, RiskReport

predictions, risk_scores = {}, {}
for p in Path('data/reports/baseline_v1').glob('*.json'):
    if p.stem == '_summary': continue
    r = RiskReport.model_validate_json(p.read_text(encoding='utf-8'))
    predictions[r.tender_id] = r.flags
    risk_scores[r.tender_id] = r.overall_risk_score

gold = {}
for line in Path('data/labeled/gold.jsonl').read_text(encoding='utf-8').splitlines():
    rec = json.loads(line)
    gold[str(rec['lot_id'])] = [Flag(**f) for f in rec['flags']]

rep = evaluate(predictions, gold)
print(rep.as_table())
auc = risk_ranking_auc(risk_scores, gold)
print(f'\nROC-AUC по risk_score: {auc:.3f}' if auc else '\nAUC: недостаточно данных')
"
```

Сохранить вывод в `docs/results.md` → раздел LLM baseline.

## 6. Что дальше

- **Расширить корпус** до 100–500 лотов: повторить шаг 2 с большим `--max-lots`, либо сделать несколько разных tinyUrl-ов (по отраслям).
- **Расширить gold** до ≥100 лотов — это даст осмысленные доверительные интервалы.
- **(Опционально) Fine-tuning** — если время и GPU позволят. См. план в `README.md` → Фаза 4.

## Полезные команды

```powershell
# Тесты (без сети)
pytest tests/ -v

# Проверить, что аккаунт Маркера живой
python -c "
import sys; sys.path.insert(0, 'src')
from tender_anomaly.ingest.marker_client import MarkerClient
with MarkerClient() as c:
    print(c.get_user_info()['Fio'])
"

# Чек, что Anthropic ключ работает
python -c "
import anthropic
r = anthropic.Anthropic().messages.create(
    model='claude-haiku-4-5', max_tokens=20,
    messages=[{'role':'user','content':'Say OK'}])
print(r.content[0].text)
"
```

## Структура проекта

```
C:\Users\Marks\Polina\
├── README.md                       # о проекте + полный план работ
├── RUN.md                          # ← ты здесь
├── pyproject.toml
├── .env.example / .env / .gitignore
├── docs/
│   ├── api-discovery.md            # карта API Маркера
│   ├── codebook.md                 # таксономия 8 меток
│   ├── progress.md                 # хронология работ
│   └── results.md                  # эмпирические результаты
├── src/tender_anomaly/
│   ├── config.py                   # пути + .env
│   ├── ingest/
│   │   ├── marker_client.py        # HTTP-клиент для Marker API
│   │   ├── downloader.py           # скачивание с zakupki.gov.ru
│   │   └── build_corpus.py         # CLI: tinyUrl → manifest + файлы
│   ├── parse/
│   │   ├── extractor.py            # PDF/DOCX/RTF → текст
│   │   └── segmenter.py            # текст → разделы (TZ/criteria/...)
│   ├── models/
│   │   ├── schema.py               # Pydantic: Flag, RiskReport
│   │   └── baseline_llm/
│   │       ├── prompts.py          # системный промпт + few-shot
│   │       └── predictor.py        # Claude API + JSON-mode
│   ├── eval/
│   │   └── metrics.py              # F1, span IoU, AUC
│   └── report/
│       └── generate.py             # CLI: manifest → risk reports
├── tests/test_smoke.py             # быстрые проверки без сети
├── data/                           # gitignored
│   ├── raw/<kind>/<lot_id>/
│   ├── labeled/gold.jsonl
│   └── reports/baseline_v1/
└── .tmp/                           # gitignored: разведочные дампы
```
