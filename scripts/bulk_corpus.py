"""Bulk-pipeline: одной командой тянем сотни реальных лотов 223-FZ из Маркера,
качаем файлы с zakupki, конвертим .doc→.docx, парсим, прогоняем LLM.

Запуск:
    # Скачать 200 лотов из violations + 100 чистых:
    python scripts/bulk_corpus.py --target 200 --kinds violations purchases

    # Только сбор данных, без LLM (LLM запускать отдельно):
    python scripts/bulk_corpus.py --target 200 --no-llm

    # Только violations:
    python scripts/bulk_corpus.py --target 300 --kinds violations

Пагинация: SearchRunFromTinyUrl возвращает первую страницу (50 лотов) +
полный объект Request с PagingParams. Используем его для последующих
SearchRun-вызовов с PageNum 2, 3, ...
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.config import RAW_DIR  # noqa: E402
from tender_anomaly.ingest.downloader import download_lot_attachments  # noqa: E402
from tender_anomaly.ingest.marker_client import (  # noqa: E402
    MarkerClient,
    attachment_urls,
    lot_violations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bulk_corpus")

# Сохранённые поиски Мунермана (из manifest, разведка ранее)
SAVED_SEARCHES = {
    "violations": [
        ("vio_223fz",  "3DAB2A3A9C55932EB82D3F4D088E5D2264D6B950"),
        ("vio_calib",  "019E104E5B929DF9A72D5841FB735D55D833BCF8"),
    ],
    "purchases": [
        ("kursovaya",  "A9CE69C80DAAE205FFC91C4687FB6258C8C696A2"),
        ("test_q1",    "FFD19555B9CC6FC05DA3C557EA73DA4A25879F74"),
        ("test_q2",    "92F54DDB12EA2E633D5450A411ACF4B68CA9A49E"),
        ("torgi_or",   "DEAEF66A450242E14E63912602D50A4C7D5AA88D"),
        ("torgi_data", "231E29F8BCCE2B288FA67789FFACD5F6035749D8"),
    ],
}


def _iter_pages(client: MarkerClient, kind: str, tiny_url: str, max_pages: int = 10):
    """Генератор страниц. Первая страница через SearchRunFromTinyUrl;
    дальше через SearchRun с тем же Request но increment-нутым PageNum."""
    if kind == "violations":
        first = client.search_violations_by_tiny_url(tiny_url)
        run_func = client.search_violations_run
    else:
        first = client.search_purchases_by_tiny_url(tiny_url)
        run_func = client.search_purchases_run

    yield first
    request = first.get("Request")
    if not request:
        return
    work_request_id = first.get("WorkRequestId")

    for page_num in range(2, max_pages + 1):
        body = dict(request)
        body["PagingParams"] = {"PageSize": 50, "PageNum": page_num}
        body["WorkRequestId"] = work_request_id
        body["UserRequestId"] = None
        body["LoadAggregates"] = False
        body["LoadResultItems"] = True
        try:
            page = run_func(body)
            time.sleep(0.4)  # throttle
        except Exception as exc:  # noqa: BLE001
            log.warning("page %d failed: %s", page_num, exc)
            return
        items = page.get("Items") or []
        if not items:
            return
        yield page


def _extract_lots_from_search(items: list[dict], kind: str) -> list[tuple[int, dict]]:
    """Из items search-а достаём (lot_id, search_item) — search_item нужен для
    плоских violations, у которых в GetLotEntity другой формат."""
    out: list[tuple[int, dict]] = []
    for item in items:
        target = item
        if kind == "violations":
            linked = item.get("LinkedLots") or []
            if not linked:
                continue
            target = linked[0]
        ent = target.get("Entity") or {}
        lot_id = ent.get("EntityId")
        if ent.get("EntityTypeId") == "Lot" and lot_id:
            out.append((lot_id, item))  # передаём ИСХОДНЫЙ item, не target
    return out


def _process_lot(
    client: MarkerClient,
    lot_id: int,
    kind: str,
    raw_dir: Path,
    skip_download: bool,
    search_item: dict | None = None,
) -> dict | None:
    """Достаёт карточку, качает аттачи, возвращает manifest record.
    search_item — оригинал из search response, оттуда берём плоские violations."""
    try:
        lot = client.get_lot(lot_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("get_lot(%s) failed: %s", lot_id, exc)
        return None

    attachments = attachment_urls(lot)
    # Violations: priority — из search item (плоский список), fallback — GetLotEntity
    violations = lot_violations(search_item) if search_item else []
    if not violations:
        violations = lot_violations(lot)
    downloaded: list[str] = []
    if not skip_download and attachments:
        try:
            paths = download_lot_attachments(lot_id, attachments, raw_dir)
            downloaded = [str(p.relative_to(raw_dir)) for p in paths]
        except Exception as exc:  # noqa: BLE001
            log.warning("download lot %s: %s", lot_id, exc)

    return {
        "lot_id": lot_id,
        "kind": kind,
        "title": lot.get("Name"),
        "source_url": (lot.get("Source") or {}).get("Url"),
        "purchase_number": (lot.get("Source") or {}).get("Number"),
        "lot_number": (lot.get("Source") or {}).get("LotNumber"),
        "source_system": (lot.get("Source") or {}).get("SourceSystem", {}).get("Name"),
        "start_price": lot.get("StartPrice"),
        "currency": lot.get("Currency"),
        "placing_way": (lot.get("PlacingWay") or {}).get("Title"),
        "is_actual": (lot.get("State") or {}).get("IsActual"),
        "customers": [
            {
                "inn": c.get("Inn"),
                "kpp": c.get("Kpp"),
                "short_name": c.get("ShortName"),
                "okato": (c.get("Okato") or {}).get("FullTitle"),
            }
            for c in (lot.get("Offerees") or [])
        ],
        "classifiers": [
            {
                "type": (cl.get("Identity") or {}).get("ClassifierTypeId"),
                "code": cl.get("Code"),
                "title": cl.get("Title"),
            }
            for cl in (lot.get("Classifiers") or [])
        ],
        "attachments": attachments,
        "downloaded_files": downloaded,
        "marker_violations": violations,
    }


@click.command()
@click.option("--target", type=int, default=200,
              help="Целевое число уникальных лотов (приоритет: violations потом purchases)")
@click.option("--kinds", multiple=True, default=["violations", "purchases"],
              type=click.Choice(["violations", "purchases"]),
              help="Какие сохранённые поиски использовать")
@click.option("--out-dir", type=click.Path(path_type=Path), default=RAW_DIR / "bulk")
@click.option("--max-pages-per-source", type=int, default=10,
              help="Сколько страниц (~50 лотов каждая) тянуть с каждого tinyUrl")
@click.option("--skip-download", is_flag=True,
              help="Только манифест, без скачивания файлов с zakupki")
@click.option("--no-convert", is_flag=True,
              help="Не запускать .doc→.docx конверсию через MS Word")
@click.option("--no-llm", is_flag=True,
              help="Не запускать LLM анализ (только сбор данных)")
@click.option("--llm-model", default="gpt-4o", help="Модель для LLM-анализа")
def main(
    target: int,
    kinds: tuple[str, ...],
    out_dir: Path,
    max_pages_per_source: int,
    skip_download: bool,
    no_convert: bool,
    no_llm: bool,
    llm_model: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    # Возобновление: читаем уже собранные lot_ids
    seen_ids: set[int] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                seen_ids.add(json.loads(line)["lot_id"])
            except Exception:  # noqa: BLE001
                continue
        log.info("resuming, %d lot_ids already in manifest", len(seen_ids))

    t_start = time.time()

    with MarkerClient(timeout=180) as client:
        info = client.get_user_info()
        log.info("logged in as %s (id=%s)", info.get("Fio"), info.get("Id"))

        manifest_file = open(manifest_path, "a", encoding="utf-8")
        n_processed = 0

        try:
            for kind in kinds:
                if n_processed >= target:
                    break
                searches = SAVED_SEARCHES.get(kind, [])
                for search_name, tiny_url in searches:
                    if n_processed >= target:
                        break
                    log.info("\n=== %s :: %s (%s) ===", kind, search_name, tiny_url[:12])
                    page_no = 0
                    for page in _iter_pages(client, kind, tiny_url, max_pages_per_source):
                        page_no += 1
                        items = page.get("Items") or []
                        log.info("  page %d: %d items", page_no, len(items))
                        lot_pairs = _extract_lots_from_search(items, kind)
                        for lot_id, search_item in lot_pairs:
                            if lot_id in seen_ids:
                                continue
                            if n_processed >= target:
                                break
                            record = _process_lot(
                                client, lot_id, kind, out_dir, skip_download,
                                search_item=search_item,
                            )
                            if not record:
                                continue
                            manifest_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                            manifest_file.flush()
                            seen_ids.add(lot_id)
                            n_processed += 1
                            n_files = len(record.get("downloaded_files") or [])
                            n_viol = len(record.get("marker_violations") or [])
                            log.info(
                                "[%d/%d] lot=%s files=%d viol=%d",
                                n_processed, target, lot_id, n_files, n_viol,
                            )
                            time.sleep(0.3)
        finally:
            manifest_file.close()

    elapsed = time.time() - t_start
    log.info("\n=== Сбор завершён: %d лотов за %.1f мин ===", n_processed, elapsed / 60)

    if skip_download:
        log.info("skip-download был включён — файлы не качали")
        return

    # Конверсия .doc → .docx
    if not no_convert:
        log.info("\n=== Конверсия .doc → .docx ===")
        subprocess.run(
            [sys.executable, "scripts/convert_doc_to_docx.py", str(out_dir)],
            check=False,
        )

    # LLM анализ
    if not no_llm:
        log.info("\n=== LLM анализ (gpt-4o) ===")
        report_dir = ROOT / "data/reports/bulk"
        subprocess.run(
            [
                sys.executable, "scripts/run_real_lots.py",
                "--root", str(out_dir),
                "--out", str(report_dir),
                "--provider", "openai", "--model", llm_model,
            ],
            check=False,
        )
        log.info("\n=== Готово ===")
        log.info("Manifest: %s", manifest_path)
        log.info("Reports:  %s", report_dir)


if __name__ == "__main__":
    main()
