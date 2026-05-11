"""Сравнение codebook v1 (data/reports/bulk/) vs v2 (data/reports/bulk_v2/)
на 30-lot subset.

Метрики:
- Кол-во флагов на лот (среднее, медиана, max)
- Per-label распределение
- Risk score distribution
- Per-lot diff (какие флаги добавлены, удалены, остались)
- Для лотов с TRUE/PARTIAL annotations — какие из них v2 сохранил
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data/reports/bulk"
V2 = ROOT / "data/reports/bulk_v2"
ANN = ROOT / "data/labeled/bulk_flag_annotations.jsonl"
OUT = ROOT / "data/reports/v1_vs_v2_comparison.md"


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


def main() -> None:
    v1 = load_reports(V1)
    v2 = load_reports(V2)
    common = sorted(set(v1) & set(v2))
    print(f"v1 reports: {len(v1)}, v2 reports: {len(v2)}, common: {len(common)}")

    # Load annotations to track signal preservation
    ann = [json.loads(l) for l in ANN.read_text(encoding="utf-8").splitlines()]
    true_partial_by_tender = defaultdict(list)
    for a in ann:
        if a["verdict"] in ("TRUE", "PARTIAL"):
            true_partial_by_tender[a["tender_id"]].append(a)

    lines = ["# Codebook v1 vs v2 — сравнение на 30-lot subset", ""]

    # ──── Sums ────
    n_flags_v1 = sum(len(v1[t]["flags"]) for t in common)
    n_flags_v2 = sum(len(v2[t]["flags"]) for t in common)
    avg_v1 = n_flags_v1 / len(common) if common else 0
    avg_v2 = n_flags_v2 / len(common) if common else 0

    risks_v1 = [v1[t]["overall_risk_score"] for t in common]
    risks_v2 = [v2[t]["overall_risk_score"] for t in common]
    avg_risk_v1 = sum(risks_v1) / len(risks_v1) if risks_v1 else 0
    avg_risk_v2 = sum(risks_v2) / len(risks_v2) if risks_v2 else 0
    high_v1 = sum(1 for r in risks_v1 if r >= 0.7)
    high_v2 = sum(1 for r in risks_v2 if r >= 0.7)
    low_v1 = sum(1 for r in risks_v1 if r < 0.3)
    low_v2 = sum(1 for r in risks_v2 if r < 0.3)

    lines += [
        "## Сводные метрики",
        "",
        "| Метрика | v1 (codebook v1) | v2 (whitelist + gating) | Δ |",
        "|---|---|---|---|",
        f"| Лотов сравнено | {len(common)} | {len(common)} | — |",
        f"| Всего флагов | {n_flags_v1} | {n_flags_v2} | {n_flags_v2-n_flags_v1:+d} ({100*(n_flags_v2-n_flags_v1)/max(n_flags_v1,1):.0f}%) |",
        f"| Avg flags/lot | {avg_v1:.1f} | {avg_v2:.1f} | {avg_v2-avg_v1:+.1f} |",
        f"| Avg risk | {avg_risk_v1:.3f} | {avg_risk_v2:.3f} | {avg_risk_v2-avg_risk_v1:+.3f} |",
        f"| High risk (≥0.7) | {high_v1}/{len(common)} | {high_v2}/{len(common)} | {high_v2-high_v1:+d} |",
        f"| Low risk (<0.3) | {low_v1}/{len(common)} | {low_v2}/{len(common)} | {low_v2-low_v1:+d} |",
        "",
    ]

    # ──── Per-label distribution ────
    labels_v1 = Counter(f["label"] for t in common for f in v1[t]["flags"])
    labels_v2 = Counter(f["label"] for t in common for f in v2[t]["flags"])
    all_labels = sorted(set(labels_v1) | set(labels_v2))

    lines += ["## Распределение меток", "",
              "| Метка | v1 | v2 | Δ |",
              "|---|---|---|---|"]
    for l in all_labels:
        a, b = labels_v1.get(l, 0), labels_v2.get(l, 0)
        lines.append(f"| `{l}` | {a} | {b} | {b-a:+d} |")
    lines.append("")

    # ──── Signal preservation: TRUE/PARTIAL flags from v1 ────
    lines += ["## Сохранение TRUE/PARTIAL сигнала из v1-разметки", ""]
    preserved = 0
    lost = 0
    for tender_id, anns in sorted(true_partial_by_tender.items()):
        if tender_id not in v2:
            continue
        v2_spans = [f["span_text"] for f in v2[tender_id]["flags"]]
        for a in anns:
            v1_span = next(
                (f["span_text"] for f in v1[tender_id]["flags"] if f["label"] == a["label"]),
                None,
            )
            # Простое сравнение: есть ли v2-span с пересечением 30+ символов c v1-span той же label
            kept = False
            if v1_span:
                for v2_span in v2_spans:
                    if (v1_span[:50] in v2_span or v2_span[:50] in v1_span):
                        kept = True
                        break
            if kept:
                preserved += 1
            else:
                lost += 1

    total_signal = preserved + lost
    if total_signal:
        lines += [
            f"- **Сохранено**: {preserved}/{total_signal} ({100*preserved/total_signal:.0f}%)",
            f"- **Потеряно**: {lost}/{total_signal} ({100*lost/total_signal:.0f}%)",
            "",
        ]
    else:
        lines += ["_(нет лотов с TRUE/PARTIAL для сравнения)_", ""]

    # ──── Per-lot diff ────
    lines += ["## Per-lot: change in flag count", "",
              "| Lot ID | v1 flags | v2 flags | Δ | risk v1 | risk v2 |",
              "|---|---|---|---|---|---|"]
    for t in common:
        v1f, v2f = len(v1[t]["flags"]), len(v2[t]["flags"])
        lines.append(
            f"| {t} | {v1f} | {v2f} | {v2f-v1f:+d} | "
            f"{v1[t]['overall_risk_score']:.2f} | {v2[t]['overall_risk_score']:.2f} |"
        )
    lines.append("")

    # ──── Bottom-10: ideally v2 should drop most flags here ────
    bottom_v1_sorted = sorted(common, key=lambda t: v1[t]["overall_risk_score"])[:8]
    lines += ["## Bottom-8 в v1 (ожидаем агрессивное снижение в v2)", "",
              "| Lot | v1 risk | v1 flags | v2 risk | v2 flags |",
              "|---|---|---|---|---|"]
    for t in bottom_v1_sorted:
        lines.append(
            f"| {t} | {v1[t]['overall_risk_score']:.2f} | {len(v1[t]['flags'])} | "
            f"{v2[t]['overall_risk_score']:.2f} | {len(v2[t]['flags'])} |"
        )
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved comparison -> {OUT}")
    print()
    # Also print key numbers to stdout
    print(f"v1: avg_flags={avg_v1:.1f} avg_risk={avg_risk_v1:.3f} high={high_v1}/{len(common)} low={low_v1}/{len(common)}")
    print(f"v2: avg_flags={avg_v2:.1f} avg_risk={avg_risk_v2:.3f} high={high_v2}/{len(common)} low={low_v2}/{len(common)}")
    if total_signal:
        print(f"Signal preservation: {preserved}/{total_signal} ({100*preserved/total_signal:.0f}%)")


if __name__ == "__main__":
    main()
