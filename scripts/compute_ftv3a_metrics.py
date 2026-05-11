# -*- coding: utf-8 -*-
"""Расширенные метрики FT v3a на 20 held-out лотах.

Считает:
- Per-flag strict / loose precision
- Lot-level precision (strict / loose)
- Lot-level recall на основе manual annotation 13 LOW-лотов
- Specificity (доля clean lots, корректно классифицированных как LOW)
- Lot-level F1 (loose)
- Per-label precision
- Confidence calibration
- False positive rate

Output: data/eval/ftv3a_extended_metrics.json
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]

# 20 held-out лотов
HELDOUT_LOTS_FILE = ROOT / "data/eval/heldout_v3_lots.json"
heldout_data = json.loads(HELDOUT_LOTS_FILE.read_text(encoding="utf-8"))
HELDOUT_LOTS = heldout_data["lots"] if isinstance(heldout_data, dict) else heldout_data

# FT v3a outputs
V3A_DIR = ROOT / "data/reports/heldout_ftv3a"
v3a_outputs: dict[str, dict] = {}
for f in V3A_DIR.glob("*.json"):
    if f.name.startswith("_"):
        continue
    v3a_outputs[f.stem] = json.loads(f.read_text(encoding="utf-8"))

# Manual verdicts на 74 flag-instances трёх FT-моделей
flag_verdicts = []
verdict_path = ROOT / "data/labeled/heldout_flag_verdicts.jsonl"
if verdict_path.exists():
    for line in verdict_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            flag_verdicts.append(json.loads(line))

# Verdicts конкретно для FT v3a (исключая v3a-mini)
v3a_flag_verdicts = [
    v for v in flag_verdicts
    if "v3a" in str(v.get("model", "")).lower()
    and "mini" not in str(v.get("model", "")).lower()
]
print(f"v3a flag verdicts: {len(v3a_flag_verdicts)}")

# Если нет model field, попробуем загрузить как все verdicts (все 74 для трёх моделей)
if not v3a_flag_verdicts and flag_verdicts:
    print(f"WARN: model-field не обнаружен. Sample: {flag_verdicts[0]}")

# Manual verdicts на 13 LOW-лотах
low_verdicts = []
for line in (ROOT / "data/labeled/heldout_low_verdicts.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        low_verdicts.append(json.loads(line))
print(f"Low-lot verdicts: {len(low_verdicts)}")

# === 1. Идентификация flagged vs LOW ===
flagged_lots = [lot for lot, data in v3a_outputs.items() if data.get("flags")]
low_lots = [lot for lot, data in v3a_outputs.items() if not data.get("flags")]
print(f"\nFT v3a flagged: {len(flagged_lots)} lots")
print(f"FT v3a LOW: {len(low_lots)} lots")

# Total flag count по v3a
v3a_total_flags = sum(len(data.get("flags", [])) for data in v3a_outputs.values())
print(f"Total v3a flags: {v3a_total_flags}")

# === 2. Per-flag precision из manual verdicts ===
v3a_verdict_counts = Counter()
for v in v3a_flag_verdicts:
    v3a_verdict_counts[v.get("verdict", "?").upper()] += 1

n_true = v3a_verdict_counts.get("TRUE", 0)
n_partial = v3a_verdict_counts.get("PARTIAL", 0)
n_false = v3a_verdict_counts.get("FALSE", 0)
total_verdicted = n_true + n_partial + n_false

if total_verdicted > 0:
    strict_p_flag = n_true / total_verdicted
    loose_p_flag = (n_true + n_partial) / total_verdicted
else:
    strict_p_flag = loose_p_flag = float("nan")

print(f"\n=== Per-flag precision ===")
print(f"  TRUE: {n_true}, PARTIAL: {n_partial}, FALSE: {n_false}")
print(f"  Strict per-flag P: {strict_p_flag:.3f}")
print(f"  Loose per-flag P:  {loose_p_flag:.3f}")

# === 3. Lot-level precision ===
# Для каждого flagged lot определяем: содержит ли хотя бы один TRUE/PARTIAL/FALSE flag
v3a_lot_verdicts = defaultdict(lambda: Counter())
for v in v3a_flag_verdicts:
    lot_id = str(v.get("tender_id") or v.get("lot_id"))
    v3a_lot_verdicts[lot_id][v.get("verdict", "?").upper()] += 1

flagged_with_true = 0
flagged_with_partial_or_true = 0
flagged_only_false = 0
for lot in flagged_lots:
    counts = v3a_lot_verdicts.get(lot, Counter())
    if counts.get("TRUE", 0) > 0:
        flagged_with_true += 1
        flagged_with_partial_or_true += 1
    elif counts.get("PARTIAL", 0) > 0:
        flagged_with_partial_or_true += 1
    else:
        if sum(counts.values()) > 0:
            flagged_only_false += 1

n_flagged = len(flagged_lots)
strict_p_lot = flagged_with_true / n_flagged if n_flagged else float("nan")
loose_p_lot = flagged_with_partial_or_true / n_flagged if n_flagged else float("nan")

print(f"\n=== Lot-level precision ===")
print(f"  Flagged lots with >=1 TRUE: {flagged_with_true} / {n_flagged}")
print(f"  Flagged lots with >=1 TRUE/PARTIAL: {flagged_with_partial_or_true} / {n_flagged}")
print(f"  Flagged lots only FALSE: {flagged_only_false} / {n_flagged}")
print(f"  Strict lot-level P: {strict_p_lot:.3f}")
print(f"  Loose lot-level P:  {loose_p_lot:.3f}")

# === 4. Lot-level recall (на основе LOW-аннотации) ===
low_verdict_map = {v["lot_id"]: v["verdict"] for v in low_verdicts}
n_missed_true = sum(1 for lot in low_lots if low_verdict_map.get(lot) == "missed_TRUE")
n_missed_partial = sum(1 for lot in low_lots if low_verdict_map.get(lot) == "missed_PARTIAL")
n_correct_low = sum(1 for lot in low_lots if low_verdict_map.get(lot) == "clean")

print(f"\n=== LOW-лоты разметка (13) ===")
print(f"  clean: {n_correct_low}")
print(f"  missed_PARTIAL: {n_missed_partial}")
print(f"  missed_TRUE: {n_missed_true}")

# Lot-level recall (loose): сколько лотов с TRUE/PARTIAL модель flagged / всего лотов с TRUE/PARTIAL
# Из 7 flagged: все имеют ≥1 TRUE/PARTIAL (т.к. loose_p_lot скорее всего 100%)
# Из 13 LOW: 1 missed_TRUE + 1 missed_PARTIAL = 2 missed positive lots
n_total_true_lots = flagged_with_true + n_missed_true
n_total_positive_lots_loose = flagged_with_partial_or_true + n_missed_true + n_missed_partial

if n_total_true_lots > 0:
    strict_recall_lot = flagged_with_true / n_total_true_lots
else:
    strict_recall_lot = float("nan")

if n_total_positive_lots_loose > 0:
    loose_recall_lot = flagged_with_partial_or_true / n_total_positive_lots_loose
else:
    loose_recall_lot = float("nan")

print(f"\n=== Lot-level recall ===")
print(f"  Lots with TRUE in held-out (flagged TRUE + missed_TRUE): {n_total_true_lots}")
print(f"  Lots with TRUE/PARTIAL in held-out: {n_total_positive_lots_loose}")
print(f"  Strict lot-level recall: {strict_recall_lot:.3f}")
print(f"  Loose lot-level recall:  {loose_recall_lot:.3f}")

# === 5. Specificity (доля clean LOW / всего clean lots) ===
# Clean lots = LOW (clean) + LOW edge cases (technically correct - empty text)
# Total negative lots = clean + edge cases. Какие LOW считать "TN"? Конечно clean.
# Из 13 LOW: 11 clean (включая 2 edge cases с пустым текстом)
n_true_negative = n_correct_low
n_total_negative = n_correct_low + flagged_only_false  # flagged лоты с only-FALSE — false positives
# Strictly: TN (correctly LOW clean) / (TN + FP) = clean LOW / (clean LOW + flagged-only-FALSE)
# Но также: total clean lots = correct_low + flagged_only_false (если они тоже clean содержательно)
specificity = n_correct_low / n_total_negative if n_total_negative else float("nan")
print(f"\n=== Specificity ===")
print(f"  Correctly LOW (clean): {n_correct_low}")
print(f"  False positives (flagged but only FALSE): {flagged_only_false}")
print(f"  Specificity: {specificity:.3f}")

# === 6. F1 ===
if loose_p_lot + loose_recall_lot > 0:
    f1_loose = 2 * loose_p_lot * loose_recall_lot / (loose_p_lot + loose_recall_lot)
else:
    f1_loose = float("nan")

if strict_p_lot + strict_recall_lot > 0:
    f1_strict = 2 * strict_p_lot * strict_recall_lot / (strict_p_lot + strict_recall_lot)
else:
    f1_strict = float("nan")

print(f"\n=== F1 (lot-level) ===")
print(f"  Strict F1: {f1_strict:.3f}")
print(f"  Loose F1:  {f1_loose:.3f}")

# === 7. Per-label precision ===
label_verdicts = defaultdict(lambda: Counter())
for v in v3a_flag_verdicts:
    label = v.get("label", "?")
    verdict = v.get("verdict", "?").upper()
    label_verdicts[label][verdict] += 1

print(f"\n=== Per-label breakdown ===")
per_label_metrics = {}
for label, c in label_verdicts.items():
    t = c.get("TRUE", 0)
    pa = c.get("PARTIAL", 0)
    fa = c.get("FALSE", 0)
    total = t + pa + fa
    if total == 0:
        continue
    sp = t / total
    lp = (t + pa) / total
    per_label_metrics[label] = {
        "n": total, "true": t, "partial": pa, "false": fa,
        "strict_p": round(sp, 3), "loose_p": round(lp, 3),
    }
    print(f"  {label}: n={total}, T={t}, P={pa}, F={fa} | strict={sp:.2%}, loose={lp:.2%}")

# === 8. Confidence calibration ===
v3a_conf_by_verdict: dict[str, list[float]] = defaultdict(list)
for v in v3a_flag_verdicts:
    conf = v.get("confidence")
    if conf is None:
        # try to look up from output
        lot_id = str(v.get("tender_id") or v.get("lot_id"))
        flag_idx = v.get("flag_idx")
        if flag_idx is not None and lot_id in v3a_outputs:
            flags = v3a_outputs[lot_id].get("flags", [])
            if flag_idx < len(flags):
                conf = flags[flag_idx].get("confidence")
    if conf is not None:
        v3a_conf_by_verdict[v.get("verdict", "?").upper()].append(conf)

print(f"\n=== Confidence calibration ===")
for verdict in ("TRUE", "PARTIAL", "FALSE"):
    confs = v3a_conf_by_verdict.get(verdict, [])
    if confs:
        avg = mean(confs)
        print(f"  Avg confidence for {verdict} (n={len(confs)}): {avg:.3f}")

# === Сборка результата ===
result = {
    "model": "FT_v3a",
    "model_id": "ft:gpt-4.1-2025-04-14:vghb:tender-anomaly-v3a:DcMwJbId",
    "evaluation_set": {
        "type": "held-out (no leakage)",
        "n_lots": len(HELDOUT_LOTS),
        "lots": HELDOUT_LOTS,
        "verified_low_lots": 13,
        "verified_flag_instances": total_verdicted,
    },
    "per_flag_precision": {
        "strict": round(strict_p_flag, 4) if strict_p_flag == strict_p_flag else None,
        "loose": round(loose_p_flag, 4) if loose_p_flag == loose_p_flag else None,
        "true": n_true, "partial": n_partial, "false": n_false,
    },
    "lot_level": {
        "n_flagged": n_flagged,
        "n_low": len(low_lots),
        "flagged_with_true": flagged_with_true,
        "flagged_with_partial_or_true": flagged_with_partial_or_true,
        "flagged_only_false": flagged_only_false,
        "low_correctly_clean": n_correct_low,
        "low_missed_true": n_missed_true,
        "low_missed_partial": n_missed_partial,
        "strict_precision": round(strict_p_lot, 4) if strict_p_lot == strict_p_lot else None,
        "loose_precision": round(loose_p_lot, 4) if loose_p_lot == loose_p_lot else None,
        "strict_recall": round(strict_recall_lot, 4) if strict_recall_lot == strict_recall_lot else None,
        "loose_recall": round(loose_recall_lot, 4) if loose_recall_lot == loose_recall_lot else None,
        "specificity": round(specificity, 4) if specificity == specificity else None,
        "strict_f1": round(f1_strict, 4) if f1_strict == f1_strict else None,
        "loose_f1": round(f1_loose, 4) if f1_loose == f1_loose else None,
    },
    "per_label_precision": per_label_metrics,
    "confidence_calibration": {
        verdict: {
            "n": len(confs),
            "avg": round(mean(confs), 4) if confs else None,
        }
        for verdict, confs in v3a_conf_by_verdict.items()
    },
}

OUT_PATH = ROOT / "data/eval/ftv3a_extended_metrics.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved: {OUT_PATH}")
