"""Калибровка whitelist heuristics: применить их к 121 флагу v1 для которого
есть ручная разметка → измерить agreement с manual verdicts.

Цель: убедиться что heuristics-based авто-разметка хотя бы коррелирует с тем,
что я делал руками.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts"))
from annotate_v2 import check_whitelist, find_context, lot_text  # noqa: E402

flags = json.loads((ROOT / "data/labeled/bulk_review_pack.json").read_text(encoding="utf-8"))
ann = [json.loads(l) for l in (ROOT / "data/labeled/bulk_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
manual_by_id = {a["flag_id"]: a["verdict"] for a in ann}

confusion = Counter()  # (manual, auto) -> count
disagreements = []

for flag in flags:
    fid = flag["flag_id"]
    manual = manual_by_id.get(fid, "?")
    full = lot_text(flag["tender_id"])
    ctx = find_context(full, flag["span_text"])
    wl, rule = check_whitelist(flag["span_text"], ctx, flag["label"])
    auto = "FALSE_W" if wl else "MAYBE_TRUE"

    # Map manual to coarse: TRUE/PARTIAL → MAYBE_TRUE, FALSE → FALSE_W
    manual_coarse = "FALSE_W" if manual == "FALSE" else "MAYBE_TRUE"
    confusion[(manual_coarse, auto)] += 1

    if manual_coarse != auto:
        disagreements.append({
            "n": flag["n"] if "n" in flag else None,
            "flag_id": fid,
            "manual": manual,
            "auto": auto,
            "rule": rule,
            "label": flag["label"],
            "span": flag["span_text"][:120],
        })

print("Confusion matrix (manual coarse vs auto):")
print(f"  manual\\auto    | MAYBE_TRUE | FALSE_W")
print(f"  MAYBE_TRUE     | {confusion.get(('MAYBE_TRUE','MAYBE_TRUE'),0):10} | {confusion.get(('MAYBE_TRUE','FALSE_W'),0):8}")
print(f"  FALSE_W        | {confusion.get(('FALSE_W','MAYBE_TRUE'),0):10} | {confusion.get(('FALSE_W','FALSE_W'),0):8}")

agree = confusion.get(("MAYBE_TRUE","MAYBE_TRUE"),0) + confusion.get(("FALSE_W","FALSE_W"),0)
total = sum(confusion.values())
print(f"\nAgreement: {agree}/{total} = {100*agree/total:.1f}%")

# Heuristics goal: high precision on FALSE_W (when auto says FALSE_W, it really is FALSE)
auto_false_total = confusion.get(("FALSE_W","FALSE_W"),0) + confusion.get(("MAYBE_TRUE","FALSE_W"),0)
if auto_false_total:
    fw_precision = confusion.get(("FALSE_W","FALSE_W"),0) / auto_false_total
    print(f"FALSE_W precision (when auto says FALSE_W, really FALSE): {fw_precision:.1%}")

# How many manual FALSE were caught by heuristics?
manual_false_total = confusion.get(("FALSE_W","MAYBE_TRUE"),0) + confusion.get(("FALSE_W","FALSE_W"),0)
if manual_false_total:
    fw_recall = confusion.get(("FALSE_W","FALSE_W"),0) / manual_false_total
    print(f"FALSE_W recall (of manual FALSE, caught by heuristics): {fw_recall:.1%}")

print(f"\nDisagreements: {len(disagreements)}")
print("\nSample disagreements:")
for d in disagreements[:20]:
    print(f"  manual={d['manual']:8s} auto={d['auto']:11s} label={d['label']:32s} rule={d['rule']:30s}")
    print(f"    span: {d['span']}")
