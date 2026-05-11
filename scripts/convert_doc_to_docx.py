"""Конверсия .doc → .docx через MS Word COM (Windows-only).

Старый формат .doc парсится только Word'ом; на Windows у пользователя есть
Office, поэтому делаем COM-автоматизацию.

Особенности:
- Один экземпляр Word на всю сессию (быстрее, меньше падений)
- Retry на 'Call was rejected by callee' (Word занят асинхронно)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Принудительно UTF-8 для stdout
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import pythoncom  # type: ignore
import win32com.client  # type: ignore

WORD_FORMAT_DOCX = 16  # wdFormatXMLDocument


def _save_with_retry(doc, target: str, retries: int = 8) -> None:
    for i in range(retries):
        try:
            doc.SaveAs2(target, FileFormat=WORD_FORMAT_DOCX)
            return
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            wait = 1.0 + i * 0.7  # 1, 1.7, 2.4, 3.1, 3.8, 4.5, 5.2, 5.9
            time.sleep(wait)
            print(f"    retry {i+1}/{retries} after {wait:.1f}s: {e}")


def main(root: Path) -> None:
    pythoncom.CoInitialize()
    word = win32com.client.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0

    docs = sorted(p for p in root.rglob("*") if p.suffix.lower() == ".doc")
    print(f"Found {len(docs)} .doc files\n")

    converted = failed = skipped = 0
    try:
        for p in docs:
            target = p.with_suffix(".docx")
            if target.exists():
                print(f"  skip (exists): {target.name}")
                skipped += 1
                continue
            print(f"  convert: {p.name}")
            try:
                # Open и save с retry, разделяем чтобы не плодить ресурсы
                for attempt in range(5):
                    try:
                        doc = word.Documents.Open(
                            str(p.absolute()),
                            ConfirmConversions=False,
                            ReadOnly=True,
                        )
                        break
                    except Exception as e:  # noqa: BLE001
                        if attempt == 4:
                            raise
                        wait = 2.0 + attempt
                        print(f"    open retry {attempt+1}/5 after {wait}s: {e}")
                        time.sleep(wait)
                _save_with_retry(doc, str(target.absolute()))
                doc.Close(SaveChanges=False)
                print(f"    OK -> {target.name}")
                converted += 1
                # Пауза чтобы Word подышал
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                print(f"    FAIL: {e}")
                failed += 1
                # При фэйле даём Word ещё больше отдышаться
                time.sleep(2.0)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()

    print(f"\nDone: {converted} converted, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/manual")
    main(root)
