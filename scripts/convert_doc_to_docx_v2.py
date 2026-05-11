"""Конверсия .doc → .docx с автоматическим рестартом Word каждые N файлов.

Старая версия использовала single Word instance на всю сессию — после
~30 конверсий Word теряет RPC connection и крашится с
'Сервер RPC недоступен' (-2147023174).

Эта версия:
- Перезапускает Word каждые BATCH_SIZE файлов
- Скипает уже сконвертированные (.docx existence check)
- Убивает зависшие WINWORD процессы перед стартом
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import pythoncom  # type: ignore
import win32com.client  # type: ignore

WORD_FORMAT_DOCX = 16
BATCH_SIZE = 25  # Restart Word every 25 conversions


def kill_word():
    """Kill all WINWORD.EXE processes."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "WINWORD.EXE"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass
    time.sleep(1)


def start_word():
    word = win32com.client.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    return word


def convert_one(word, p: Path, target: Path) -> bool:
    """Returns True if successful."""
    for attempt in range(3):
        try:
            doc = word.Documents.Open(
                str(p.absolute()),
                ConfirmConversions=False,
                ReadOnly=True,
            )
            doc.SaveAs2(str(target.absolute()), FileFormat=WORD_FORMAT_DOCX)
            doc.Close(SaveChanges=False)
            return True
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"    FAIL after 3 retries: {e}")
                return False
            wait = 1.5 + attempt
            print(f"    retry {attempt+1}/3 after {wait}s: {e}")
            time.sleep(wait)
    return False


def main(root: Path) -> None:
    print("Killing existing WINWORD.EXE processes...")
    kill_word()
    pythoncom.CoInitialize()

    docs = sorted(p for p in root.rglob("*") if p.suffix.lower() == ".doc")
    print(f"Found {len(docs)} .doc files\n")

    word = start_word()
    converted = failed = skipped = 0
    in_batch = 0

    try:
        for i, p in enumerate(docs, 1):
            target = p.with_suffix(".docx")
            if target.exists():
                skipped += 1
                continue

            print(f"[{i}/{len(docs)}] convert: {p.name}")

            # Periodic Word restart
            if in_batch >= BATCH_SIZE:
                print(f"  --- Word restart (batch of {BATCH_SIZE} done) ---")
                try:
                    word.Quit()
                except Exception:
                    pass
                kill_word()
                word = start_word()
                in_batch = 0

            ok = convert_one(word, p, target)
            if ok:
                print(f"  OK -> {target.name}")
                converted += 1
            else:
                # Try restart Word after FAIL
                print(f"  --- Word restart after FAIL ---")
                try:
                    word.Quit()
                except Exception:
                    pass
                kill_word()
                word = start_word()
                in_batch = 0
                # One more shot
                ok = convert_one(word, p, target)
                if ok:
                    print(f"  OK on second attempt -> {target.name}")
                    converted += 1
                else:
                    failed += 1

            in_batch += 1
            time.sleep(0.4)

    finally:
        try:
            word.Quit()
        except Exception:
            pass
        kill_word()
        pythoncom.CoUninitialize()

    print(f"\nDone: {converted} converted, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw/bulk")
    main(root)
