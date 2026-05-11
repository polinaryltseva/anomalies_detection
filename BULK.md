# Bulk pipeline — массовый сбор и анализ лотов

Один скрипт делает всё: тянет 200+ лотов из Маркера с пагинацией, качает файлы с zakupki, конвертит .doc→.docx, прогоняет LLM, сохраняет risk reports.

## Перед запуском

1. Закрой тяжёлые приложения (Chrome, Discord, Steam).
2. Подключи зарядку — будет работать долго.
3. Куки Маркера в `.env` живые (если нет — обнови через DevTools).
4. На диске **20–30 GB свободно** под файлы (200 лотов × ~7 файлов × ~500KB).
5. Бюджет API: **gpt-4o ~$30** на 200 лотов (если на mini — $3).

## Команды

### Полный прогон 200 лотов (рекомендую)

```powershell
cd C:\Users\Marks\Polina
python scripts/bulk_corpus.py --target 200 --kinds violations purchases
```

**Что делает:**
1. Логинится в Маркер (используя куки из `.env`).
2. Тянет лоты по 50 на страницу из 7 сохранённых поисков:
   - `vio_223fz`, `vio_calib` (нарушения 223-ФЗ)
   - `kursovaya`, `test_q1`, `test_q2`, `torgi_or`, `torgi_data` (обычные закупки)
3. Для каждого лота: GetLotEntity → metadata + ссылки на аттачи.
4. Качает аттачи с zakupki.gov.ru → `data/raw/bulk/<lot_id>/`.
5. Конвертит .doc → .docx через MS Word (нужен Office).
6. Запускает LLM-анализ (gpt-4o) → reports в `data/reports/bulk/<lot_id>.json`.

**Время**: 4–6 часов end-to-end. Можно прервать (Ctrl+C) и продолжить — будет дописывать manifest.

### Только сбор данных (без LLM)

```powershell
python scripts/bulk_corpus.py --target 300 --no-llm
```

LLM можно запустить отдельно потом:
```powershell
python scripts/run_real_lots.py --root data/raw/bulk --out data/reports/bulk --provider openai --model gpt-4o
```

### Дешёвая модель

```powershell
python scripts/bulk_corpus.py --target 200 --llm-model gpt-4o-mini
```

gpt-4o-mini в **20 раз дешевле**, precision немного ниже но для бытового анализа норм. **~$1.50 на 200 лотов** вместо $30.

### Только manifest (для проверки доступа Маркера)

```powershell
python scripts/bulk_corpus.py --target 50 --skip-download --no-convert --no-llm
```

5 минут, проверяет что куки живые и API работает. Файлы не качает.

## Прогресс / возобновление

Манифест пишется построчно в `data/raw/bulk/manifest.jsonl`. Если процесс прервался — перезапуск **продолжит с того места**, не будет качать заново уже скачанные лоты.

Контроль прогресса в отдельном терминале:
```powershell
Get-Content data\raw\bulk\manifest.jsonl | Measure-Object -Line
ls data\reports\bulk | Measure-Object  # сколько risk-report-ов готово
```

## Возможные ошибки

- **«401 Unauthorized»** — кука протухла, обнови `MARKER_SESSION_TICKET` в `.env`.
- **«ReadTimeout»** — Маркер тормозит, скрипт сам ретраит. Если упёрся — перезапусти.
- **Word COM «Вызов был отклонён»** — Word занят. Скрипт ретраит. Если все 8 попыток фэйл — закрой все Word окна и перезапусти.
- **OpenAI 429 (rate limit)** — SDK ретраит автоматически. Если совсем долго — добавь `--llm-model gpt-4o-mini` (другой rate limit pool).

## После завершения

Аналитика готова в `data/reports/bulk/`. Дальше:

```powershell
# Свести метрики в один отчёт
python -c "
import json
from pathlib import Path
from collections import Counter

reports = sorted(p for p in Path('data/reports/bulk').glob('*.json') if p.name != '_summary.json')
risks = []
labels = Counter()
for f in reports:
    r = json.loads(f.read_text(encoding='utf-8'))
    risks.append((r['tender_id'], r['overall_risk_score'], r['risk_level'], len(r['flags'])))
    for fl in r['flags']: labels[fl['label']] += 1

risks.sort(key=lambda x: -x[1])
print(f'Total: {len(reports)} lots, avg risk: {sum(r[1] for r in risks)/len(risks):.2f}')
print(f'High: {sum(1 for r in risks if r[2]==\"high\")}, Medium: {sum(1 for r in risks if r[2]==\"medium\")}, Low: {sum(1 for r in risks if r[2]==\"low\")}')
print()
print('Top 10 by risk:')
for lot, risk, level, n in risks[:10]:
    print(f'  {lot:20s} risk={risk:.2f}  flags={n}')
print()
print('Label distribution:')
for lbl, n in labels.most_common():
    print(f'  {n:4d}  {lbl}')
"
```

Можно повторить ручную разметку на новой выборке через `scripts/prepare_review_pack.py` (направить на новый report dir).
