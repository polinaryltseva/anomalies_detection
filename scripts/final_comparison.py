"""Финальное сравнение v1 / v2 / v2+2stage на пересекающемся подмножестве лотов.

Главные метрики:
1. Risk distribution (LOW/MEDIUM/HIGH) — discriminative power
2. Avg flags/lot
3. Heuristic precision_upper (на основе validated whitelist heuristics)
4. Estimated real precision (with heuristic recall calibration)
5. Per-label distribution
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from annotate_v2 import check_whitelist, find_context, lot_text  # noqa: E402

DIRS = {
    "v1 (codebook v1)": ROOT / "data/reports/bulk",
    "v2 (whitelist + gating)": ROOT / "data/reports/bulk_v2",
    "v2 + 2-stage validator": ROOT / "data/reports/bulk_v2_2stage",
    "v3 (W1-W15) + 2-stage": ROOT / "data/reports/bulk_v3",
}

OUT = ROOT / "data/reports/final_v1_v2_2stage_comparison.md"

# Heuristic recall calibration from validate_heuristics.py: 68.6% on real FALSE
HEURISTIC_FP_RECALL = 0.686


def load_reports(d: Path) -> dict[str, dict]:
    out = {}
    for p in sorted(d.glob("*.json")):
        if p.name == "_summary.json":
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            out[r["tender_id"]] = r
        except Exception:
            continue
    return out


def annotate(reports: dict[str, dict]) -> tuple[int, int, dict]:
    """Returns (n_flags, n_false_w, by_label)."""
    n = 0
    n_false_w = 0
    by_label = defaultdict(lambda: {"total": 0, "false_w": 0})
    for r in reports.values():
        full = lot_text(r["tender_id"])
        for f in r["flags"]:
            n += 1
            ctx = find_context(full, f["span_text"])
            wl, _ = check_whitelist(f["span_text"], ctx, f["label"])
            by_label[f["label"]]["total"] += 1
            if wl:
                n_false_w += 1
                by_label[f["label"]]["false_w"] += 1
    return n, n_false_w, dict(by_label)


def main() -> None:
    pipelines = {name: load_reports(d) for name, d in DIRS.items()}
    common_lots = set(pipelines["v1 (codebook v1)"])
    for ps in pipelines.values():
        common_lots &= set(ps)
    common_lots = sorted(common_lots)
    print(f"Common lots across all pipelines: {len(common_lots)}")

    # Filter to common lots only
    pipelines = {name: {t: r for t, r in p.items() if t in common_lots} for name, p in pipelines.items()}

    lines = [f"# v1 vs v2 vs v2+2stage — финальное сравнение на {len(common_lots)} лотах", ""]

    # 1. Headline table
    lines += ["## Сводная таблица", "",
              "| Метрика | v1 | v2 | v2+2stage |",
              "|---|---|---|---|"]
    headline = {}
    for name, reports in pipelines.items():
        n_lots = len(reports)
        n_flags = sum(len(r["flags"]) for r in reports.values())
        avg_flags = n_flags / n_lots if n_lots else 0
        risks = [r["overall_risk_score"] for r in reports.values()]
        avg_risk = sum(risks) / len(risks) if risks else 0
        high = sum(1 for x in risks if x >= 0.7)
        med = sum(1 for x in risks if 0.3 <= x < 0.7)
        low = sum(1 for x in risks if x < 0.3)
        n_total, n_fw, by_label = annotate(reports)
        heuristic_fp_rate = n_fw / n_total if n_total else 0
        # Adjust for heuristic recall: estimated real FP rate
        est_real_fp = min(1.0, heuristic_fp_rate / HEURISTIC_FP_RECALL) if heuristic_fp_rate else 0
        est_real_tp = 1 - est_real_fp
        headline[name] = {
            "n_lots": n_lots,
            "n_flags": n_flags,
            "avg_flags": avg_flags,
            "avg_risk": avg_risk,
            "high": high, "med": med, "low": low,
            "heuristic_fp_rate": heuristic_fp_rate,
            "est_real_tp": est_real_tp,
            "by_label": by_label,
        }

    rows = [
        ("Лотов", "n_lots", "{:d}"),
        ("Всего флагов", "n_flags", "{:d}"),
        ("Avg flags/lot", "avg_flags", "{:.1f}"),
        ("Avg risk", "avg_risk", "{:.3f}"),
        ("HIGH lots (≥0.7)", "high", "{:d}"),
        ("MEDIUM lots (0.3-0.7)", "med", "{:d}"),
        ("LOW lots (<0.3)", "low", "{:d}"),
        ("Heuristic FALSE_W rate", "heuristic_fp_rate", "{:.1%}"),
        ("**Est. real precision**", "est_real_tp", "**{:.1%}**"),
    ]
    keys = list(pipelines.keys())
    for label, key, fmt in rows:
        cells = [fmt.format(headline[k][key]) for k in keys]
        lines.append(f"| {label} | {' | '.join(cells)} |")
    lines.append("")

    # 2. Per-label
    lines += ["## Per-label распределение и точность", "",
              "| Метка | v1 (FP%) | v2 (FP%) | v2+2s (FP%) | v1 → v2+2s |",
              "|---|---|---|---|---|"]
    all_labels = set()
    for h in headline.values():
        all_labels |= set(h["by_label"].keys())
    for label in sorted(all_labels):
        cells = []
        for k in keys:
            d = headline[k]["by_label"].get(label, {"total": 0, "false_w": 0})
            t = d["total"]
            f_w = d["false_w"]
            if t == 0:
                cells.append("-")
            else:
                cells.append(f"{t} ({100*f_w/t:.0f}%)")
        # Compute v1 -> v2+2s direction
        v1_total = headline[keys[0]]["by_label"].get(label, {"total": 0})["total"]
        v3_total = headline[keys[2]]["by_label"].get(label, {"total": 0})["total"]
        delta = f"{v1_total} -> {v3_total}"
        lines.append(f"| `{label}` | {cells[0]} | {cells[1]} | {cells[2]} | {delta} |")
    lines.append("")

    # 3. Risk distribution
    lines += ["## Дискриминативная сила: risk distribution", ""]
    for k in keys:
        h = headline[k]
        total = h["high"] + h["med"] + h["low"]
        if total == 0:
            continue
        lines.append(f"**{k}** ({total} лотов):")
        lines.append(f"- HIGH (≥0.7): {h['high']}/{total} ({100*h['high']/total:.0f}%)")
        lines.append(f"- MEDIUM (0.3-0.7): {h['med']}/{total} ({100*h['med']/total:.0f}%)")
        lines.append(f"- LOW (<0.3): {h['low']}/{total} ({100*h['low']/total:.0f}%)")
        lines.append("")

    # 4. Per-lot side-by-side
    lines += ["## Per-lot: risk + flag count", "",
              "| Lot | v1 risk / flags | v2 risk / flags | v2+2s risk / flags |",
              "|---|---|---|---|"]
    for lot in common_lots:
        cells = []
        for k in keys:
            r = pipelines[k][lot]
            cells.append(f"{r['overall_risk_score']:.2f} / {len(r['flags'])}")
        lines.append(f"| `{lot}` | {' | '.join(cells)} |")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved -> {OUT}")
    print()
    for k in keys:
        h = headline[k]
        print(f"{k}:")
        print(f"  flags={h['n_flags']}/{h['n_lots']} avg={h['avg_flags']:.1f} risk={h['avg_risk']:.3f}")
        print(f"  HIGH/MED/LOW = {h['high']}/{h['med']}/{h['low']}")
        print(f"  Heuristic FP rate: {h['heuristic_fp_rate']:.1%}; est real precision: {h['est_real_tp']:.1%}")


if __name__ == "__main__":
    main()
