"""Скачивание тендерной документации с zakupki.gov.ru.

URLs приходят из карточки лота Marker (.Attachments[*].Url). Они публичные,
но реально доступны только из России (geo-блок снаружи).
Скачиваем потоком, проверяем размер и MIME, кидаем DownloadError на проблемы.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB safety cap
SAFE_NAME_RE = re.compile(r"[^\w.\-]+", re.UNICODE)


class DownloadError(RuntimeError):
    pass


def _safe_filename(name: str | None, fallback: str) -> str:
    if not name:
        return fallback
    s = SAFE_NAME_RE.sub("_", name).strip("._")
    return s[:200] or fallback


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
def download_file(
    url: str,
    target_dir: Path,
    file_name: str | None = None,
    timeout: float = 60.0,
) -> Path:
    """Скачивает один файл, возвращает путь.
    Имя файла: <file_name> (если задано) либо MD5(url)+ext."""
    target_dir.mkdir(parents=True, exist_ok=True)
    fallback = hashlib.md5(url.encode()).hexdigest()
    safe_name = _safe_filename(file_name, fallback)
    target = target_dir / safe_name
    if target.exists() and target.stat().st_size > 0:
        log.debug("skip (exists): %s", target)
        return target

    headers = {"User-Agent": "Mozilla/5.0 (compatible; TenderAnomalyResearch/0.1)"}
    with httpx.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as r:
        if r.status_code != 200:
            raise DownloadError(f"HTTP {r.status_code} for {url}")
        total = 0
        with open(target, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    f.close()
                    target.unlink(missing_ok=True)
                    raise DownloadError(f"File >{MAX_FILE_BYTES} bytes: {url}")
                f.write(chunk)
    if total == 0:
        target.unlink(missing_ok=True)
        raise DownloadError(f"Empty body from {url}")
    log.info("downloaded %s (%d bytes)", target.name, total)
    return target


def download_lot_attachments(
    lot_id: int,
    attachments: list[dict],
    base_dir: Path,
) -> list[Path]:
    """Качает все вложения лота в base_dir/<lot_id>/. Возвращает список локальных путей."""
    target_dir = base_dir / str(lot_id)
    saved: list[Path] = []
    for att in attachments:
        url = att.get("url")
        if not url:
            continue
        try:
            saved.append(download_file(url, target_dir, att.get("file_name")))
        except Exception as exc:  # noqa: BLE001
            log.warning("failed %s: %s", url, exc)
    return saved
