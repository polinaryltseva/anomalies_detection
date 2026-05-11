"""Сборка корпуса: пробегает страницы SearchRunFromTinyUrl, тянет GetLotEntity,
скачивает аттачи, пишет manifest JSONL.

Запуск:
    python -m tender_anomaly.ingest.build_corpus \\
        --tiny-url 3DAB2A3A9C55932EB82D3F4D088E5D2264D6B950 \\
        --kind violations \\
        --max-lots 50

Результат:
    data/raw/<kind>/<lot_id>/<file_name>.{pdf,docx,...}
    data/raw/<kind>/manifest.jsonl  — по строке на лот
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Literal

import click

from tender_anomaly.config import RAW_DIR
from tender_anomaly.ingest.downloader import download_lot_attachments
from tender_anomaly.ingest.marker_client import (
    MarkerClient,
    attachment_urls,
    lot_violations,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

Kind = Literal["purchases", "violations"]


def _run_search(client: MarkerClient, tiny_url: str, kind: Kind) -> dict:
    if kind == "violations":
        return client.search_violations_by_tiny_url(tiny_url)
    return client.search_purchases_by_tiny_url(tiny_url)


@click.command()
@click.option("--tiny-url", required=True, help="hash из SavedRequestUrl")
@click.option("--kind", type=click.Choice(["purchases", "violations"]), default="violations")
@click.option("--max-lots", type=int, default=50, show_default=True)
@click.option("--skip-download", is_flag=True, help="Не скачивать файлы, только метаданные")
@click.option("--throttle", type=float, default=0.4, show_default=True)
def main(tiny_url: str, kind: Kind, max_lots: int, skip_download: bool, throttle: float) -> None:
    out_dir = RAW_DIR / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    seen_ids: set[int] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                seen_ids.add(json.loads(line)["lot_id"])
            except Exception:  # noqa: BLE001
                continue
        log.info("resuming, %d lot_ids уже в manifest", len(seen_ids))

    with MarkerClient() as client:
        info = client.get_user_info()
        log.info("logged in as %s (id=%s)", info.get("Fio"), info.get("Id"))

        page = _run_search(client, tiny_url, kind)
        total_avail = page.get("Total", 0)
        items = page.get("Items", [])
        log.info("search: total=%s items_in_page=%s", total_avail, len(items))

        with open(manifest_path, "a", encoding="utf-8") as mf:
            n_processed = 0
            for item in items:
                if n_processed >= max_lots:
                    break
                # для violations — лот находится внутри LinkedLots[0]
                target = item
                if kind == "violations":
                    linked = item.get("LinkedLots") or []
                    if not linked:
                        continue
                    target = linked[0]
                ent = target.get("Entity") or {}
                if ent.get("EntityTypeId") != "Lot":
                    continue
                lot_id = ent.get("EntityId")
                if not lot_id or lot_id in seen_ids:
                    continue

                try:
                    lot = client.get_lot(lot_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning("lot %s fetch failed: %s", lot_id, exc)
                    continue

                attachments = attachment_urls(lot)
                violations = lot_violations(item) or lot_violations(lot)

                downloaded: list[str] = []
                if not skip_download and attachments:
                    paths = download_lot_attachments(lot_id, attachments, out_dir)
                    downloaded = [str(p.relative_to(out_dir)) for p in paths]

                record = {
                    "lot_id": lot_id,
                    "kind": kind,
                    "tiny_url": tiny_url,
                    "title": lot.get("Name") or item.get("Title"),
                    "source_url": (lot.get("Source") or {}).get("Url"),
                    "purchase_number": (lot.get("Source") or {}).get("Number"),
                    "lot_number": (lot.get("Source") or {}).get("LotNumber"),
                    "source_system": (lot.get("Source") or {}).get("SourceSystem", {}).get("Name"),
                    "start_price": lot.get("StartPrice"),
                    "currency": lot.get("Currency"),
                    "date_from": item.get("DateFrom"),
                    "date_to": item.get("DateTo"),
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
                mf.write(json.dumps(record, ensure_ascii=False) + "\n")
                mf.flush()
                seen_ids.add(lot_id)
                n_processed += 1
                log.info(
                    "[%d/%d] lot=%s files=%d viol=%d",
                    n_processed, max_lots, lot_id, len(downloaded), len(violations),
                )
                time.sleep(throttle)

    log.info("done. manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
