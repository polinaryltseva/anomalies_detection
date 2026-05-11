"""Generate VKR-quality charts for results section.

Produces PNG visualizations:
1. Risk distribution histograms (4 pipelines side-by-side)
2. Flag count per lot scatter (v1 vs v3 vs ensemble)
3. Per-label precision heatmap
4. Pipeline progression bar chart (FP rate decreasing)
5. Bottom-10 risk comparison (clean lots correctly identified)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs/charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DIRS = {
    "v1": ROOT / "data/reports/bulk",
    "v3+2stage": ROOT / "data/reports/bulk_v3",
    "ensemble": ROOT / "data/reports/bulk_ensemble",
    "FT v1": ROOT / "data/reports/bulk_ft",
    "FT v2": ROOT / "data/reports/bulk_ft_v2",
}

PIPELINE_COLOURS = {
    "v1": "#d62728",        # red
    "v3+2stage": "#1f77b4",  # blue
    "ensemble": "#9467bd",   # purple
    "FT v1": "#2ca02c",      # green
    "FT v2": "#17becf",      # cyan
}


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


def chart_1_risk_distribution(pipelines: dict[str, dict[str, dict]], common: list[str]) -> None:
    """Histogram of risk scores per pipeline, side-by-side."""
    fig, axes = plt.subplots(1, len(pipelines), figsize=(20, 4.5), sharey=True)
    bins = np.linspace(0, 1, 21)

    for ax, (name, reports) in zip(axes, pipelines.items()):
        risks = [reports[t]["overall_risk_score"] for t in common if t in reports]
        ax.hist(risks, bins=bins, color=PIPELINE_COLOURS.get(name, "gray"),
                edgecolor="black", alpha=0.85)
        ax.axvspan(0.0, 0.3, alpha=0.05, color="green", label="LOW")
        ax.axvspan(0.3, 0.7, alpha=0.05, color="orange", label="MED")
        ax.axvspan(0.7, 1.0, alpha=0.05, color="red", label="HIGH")
        ax.set_title(f"{name}\n(n={len(risks)} lots)", fontsize=11)
        ax.set_xlabel("risk_score")
        ax.set_xlim(0, 1)
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Number of lots")
    fig.suptitle("Distribution of risk scores across pipelines (30-lot subset)",
                 fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "01_risk_distribution.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved 01_risk_distribution.png")


def chart_2_flag_count_progression(pipelines: dict, common: list[str]) -> None:
    """Bar chart: avg flags per lot across pipelines."""
    fig, ax = plt.subplots(figsize=(10, 5))
    names = list(pipelines.keys())
    avgs = []
    totals = []
    for name in names:
        reports = pipelines[name]
        n_flags = sum(len(reports[t]["flags"]) for t in common if t in reports)
        n_lots = sum(1 for t in common if t in reports)
        avgs.append(n_flags / n_lots if n_lots else 0)
        totals.append(n_flags)

    bars = ax.bar(names, avgs, color=[PIPELINE_COLOURS.get(n, "gray") for n in names],
                   edgecolor="black", linewidth=1.5)
    for bar, total, avg in zip(bars, totals, avgs):
        ax.annotate(f"{avg:.1f}\n({total} total)",
                    xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Average flags per lot")
    ax.set_title("Flag count reduction across pipeline iterations\n(same 30 lots)",
                 fontsize=13)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "02_flag_count_progression.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Saved 02_flag_count_progression.png")


def chart_3_risk_level_stacked(pipelines: dict, common: list[str]) -> None:
    """Stacked bar: HIGH/MED/LOW lot counts per pipeline."""
    fig, ax = plt.subplots(figsize=(10, 5))
    names = list(pipelines.keys())
    high, med, low = [], [], []
    for name in names:
        reports = pipelines[name]
        risks = [reports[t]["overall_risk_score"] for t in common if t in reports]
        high.append(sum(1 for r in risks if r >= 0.7))
        med.append(sum(1 for r in risks if 0.3 <= r < 0.7))
        low.append(sum(1 for r in risks if r < 0.3))

    x = np.arange(len(names))
    bar_w = 0.65
    p1 = ax.bar(x, high, bar_w, label="HIGH (≥0.7)", color="#d62728")
    p2 = ax.bar(x, med, bar_w, bottom=high, label="MEDIUM (0.3-0.7)", color="#ff7f0e")
    p3 = ax.bar(x, low, bar_w, bottom=[h+m for h,m in zip(high, med)],
                label="LOW (<0.3)", color="#2ca02c")

    for i, name in enumerate(names):
        bases = [0, high[i], high[i] + med[i]]
        vals = [high[i], med[i], low[i]]
        for j, (val, color) in enumerate(zip(vals, ["white", "white", "white"])):
            if val > 0:
                ax.text(i, bases[j] + val/2, str(val), ha="center", va="center",
                        color="white", fontweight="bold", fontsize=11)

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Number of lots")
    ax.set_title("Risk-level distribution across pipelines (30 lots)\n"
                 "Только v2+2stage и ensemble дают LOW-классификацию",
                 fontsize=13)
    ax.legend(loc="lower right")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "03_risk_level_distribution.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Saved 03_risk_level_distribution.png")


def chart_4_bottom10_specificity(pipelines: dict) -> None:
    """Bottom-10 risk comparison — line chart showing how each pipeline scores
    manually-verified-clean lots."""
    bottom = ['169629544', '169596415', '169608004', '169633366', '169618156',
              '169608015', '169633302', '169618157']
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(bottom))
    for name, reports in pipelines.items():
        risks = []
        for t in bottom:
            if t in reports:
                risks.append(reports[t]["overall_risk_score"])
            else:
                risks.append(np.nan)
        ax.plot(x, risks, marker="o", label=name, linewidth=2, markersize=8,
                color=PIPELINE_COLOURS.get(name, "gray"))

    ax.axhline(0.7, color="red", linestyle="--", alpha=0.5, label="HIGH threshold")
    ax.axhline(0.3, color="orange", linestyle="--", alpha=0.5, label="MED threshold")
    ax.set_xticks(x)
    ax.set_xticklabels([t[-4:] for t in bottom], rotation=45)
    ax.set_xlabel("Lot ID (last 4 digits)")
    ax.set_ylabel("Risk score")
    ax.set_title("Specificity test: bottom-8 manually-verified-clean lots\n"
                 "Идеальный pipeline должен давать <0.3 (LOW)",
                 fontsize=13)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "04_bottom10_specificity.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Saved 04_bottom10_specificity.png")


def chart_5_per_label_distribution(pipelines: dict, common: list[str]) -> None:
    """Heatmap: pipeline × label → flag count."""
    LABELS = ["brand_or_model_targeting", "restrictive_tech_specs",
              "disproportionate_qualification", "documentary_burden",
              "ambiguous_evaluation_criteria", "unusual_short_deadlines",
              "unusual_contract_terms", "conflict_of_interest_signals"]
    pipe_names = list(pipelines.keys())
    matrix = np.zeros((len(pipe_names), len(LABELS)), dtype=int)
    for i, name in enumerate(pipe_names):
        reports = pipelines[name]
        c = Counter()
        for t in common:
            if t in reports:
                for f in reports[t]["flags"]:
                    c[f["label"]] += 1
        for j, lbl in enumerate(LABELS):
            matrix[i, j] = c.get(lbl, 0)

    fig, ax = plt.subplots(figsize=(13, 5))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(np.arange(len(LABELS)))
    ax.set_xticklabels([l.replace("_", "\n") for l in LABELS], rotation=0, fontsize=8)
    ax.set_yticks(np.arange(len(pipe_names)))
    ax.set_yticklabels(pipe_names)
    for i in range(len(pipe_names)):
        for j in range(len(LABELS)):
            v = matrix[i, j]
            ax.text(j, i, str(v), ha="center", va="center",
                    color="black" if v < matrix.max()/2 else "white", fontsize=10)
    ax.set_title("Flag count by pipeline × label (30 lots)", fontsize=13)
    fig.colorbar(im, ax=ax, label="N flags")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "05_label_heatmap.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("Saved 05_label_heatmap.png")


def main() -> None:
    pipelines = {n: load_reports(d) for n, d in DIRS.items() if d.exists()}
    pipelines = {k: v for k, v in pipelines.items() if v}
    print(f"Loaded pipelines: {list(pipelines.keys())}")
    common = sorted(set.intersection(*(set(p) for p in pipelines.values())))
    print(f"Common lots: {len(common)}")

    chart_1_risk_distribution(pipelines, common)
    chart_2_flag_count_progression(pipelines, common)
    chart_3_risk_level_stacked(pipelines, common)
    chart_4_bottom10_specificity(pipelines)
    chart_5_per_label_distribution(pipelines, common)
    print(f"\nAll charts -> {OUT_DIR}")


if __name__ == "__main__":
    main()
