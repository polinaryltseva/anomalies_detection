"""Generate held-out evaluation chart — the MOST DEFENSIBLE metric for VKR."""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

held_out = ['169601988', '169625654', '169607912', '169633468', '169608001',
            '169596411', '169633409', '169629628', '169632529', '169618150',
            '169614080', '169632308', '169625569', '169618154', '169548312',
            '169638017', '169633404', '169602026', '169568252', '169629511']


def load_risks(d: str, lots: list[str]) -> list[float]:
    out = []
    for t in lots:
        p = f"{d}/{t}.json"
        if os.path.exists(p):
            r = json.loads(open(p, encoding="utf-8").read())
            out.append(r["overall_risk_score"])
        else:
            out.append(np.nan)
    return out


pipelines = {
    "v1 baseline": "data/reports/bulk",
    "v3+2stage\n(gpt-4o-mini)": "data/reports/bulk_v3",
    "Rule detector\n(regex)": "data/reports/bulk_rules",
    "FT v1\n(122 ex)": "data/reports/bulk_ft",
    "FT v2\n(204 ex)": "data/reports/bulk_ft_v2",
}

risks_per = {n: load_risks(d, held_out) for n, d in pipelines.items()}

# ─── Chart: side-by-side bars showing risk distribution per pipeline ───
fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))

# Left: stacked HIGH/MED/LOW bars
ax1 = axes[0]
names = list(pipelines.keys())
high, med, low = [], [], []
for name in names:
    rs = [r for r in risks_per[name] if not np.isnan(r)]
    high.append(sum(1 for r in rs if r >= 0.7))
    med.append(sum(1 for r in rs if 0.3 <= r < 0.7))
    low.append(sum(1 for r in rs if r < 0.3))

x = np.arange(len(names))
ax1.bar(x, high, label="HIGH (≥0.7)", color="#d62728", edgecolor="black")
ax1.bar(x, med, bottom=high, label="MEDIUM (0.3-0.7)", color="#ff7f0e", edgecolor="black")
ax1.bar(x, low, bottom=[h+m for h, m in zip(high, med)],
        label="LOW (<0.3)", color="#2ca02c", edgecolor="black")

for i, name in enumerate(names):
    bases = [0, high[i], high[i] + med[i]]
    vals = [high[i], med[i], low[i]]
    for j, val in enumerate(vals):
        if val > 0:
            ax1.text(i, bases[j] + val / 2, str(val), ha="center", va="center",
                     color="white", fontweight="bold", fontsize=12)

ax1.set_xticks(x)
ax1.set_xticklabels(names, fontsize=9)
ax1.set_ylabel("Number of lots (out of 20)")
ax1.set_title("Held-out evaluation: 20 lots NOT in training\n(никакого data leakage)",
              fontsize=12)
ax1.legend(loc="lower left", fontsize=9)
ax1.grid(True, axis="y", alpha=0.3)

# Right: per-lot risk lines
ax2 = axes[1]
colors = {"v1 baseline": "#d62728", "v3+2stage\n(gpt-4o-mini)": "#1f77b4",
          "Rule detector\n(regex)": "#9467bd", "FT v1\n(122 ex)": "#2ca02c",
          "FT v2\n(204 ex)": "#17becf"}
xs = np.arange(len(held_out))
for name in names:
    rs = risks_per[name]
    ax2.plot(xs, rs, marker="o", label=name.replace("\n", " "),
             color=colors.get(name, "gray"), markersize=6, alpha=0.8, linewidth=1.5)

ax2.axhline(0.7, color="red", linestyle="--", alpha=0.4, label="HIGH threshold")
ax2.axhline(0.3, color="orange", linestyle="--", alpha=0.4, label="MED threshold")
ax2.set_xticks(xs)
ax2.set_xticklabels([t[-4:] for t in held_out], rotation=45, fontsize=8)
ax2.set_ylim(-0.05, 1.05)
ax2.set_xlabel("Lot ID (last 4 digits)")
ax2.set_ylabel("risk_score")
ax2.set_title("Per-lot risk on 20 held-out (новые тендеры)", fontsize=12)
ax2.legend(loc="lower right", fontsize=8)
ax2.grid(True, alpha=0.3)

# Annotate generalization findings
for i, t in enumerate(held_out):
    if t in ("169625569", "169638017"):
        ax2.annotate("«Не предусмотрено»\nTRUE pattern", xy=(i, risks_per["FT v1\n(122 ex)"][i]),
                     xytext=(i, 0.85), fontsize=8, ha="center",
                     arrowprops=dict(arrowstyle="->", color="green", alpha=0.6),
                     color="green", fontweight="bold")

fig.suptitle("Held-out validation: real generalization of FT gpt-4.1", fontsize=14, y=1.02)
fig.tight_layout()

out = ROOT / "docs/charts/07_heldout_validation.png"
fig.savefig(out, dpi=120, bbox_inches="tight")
plt.close(fig)
print(f"Saved -> {out}")

# Print summary
for name in names:
    rs = [r for r in risks_per[name] if not np.isnan(r)]
    h = sum(1 for r in rs if r >= 0.7)
    m = sum(1 for r in rs if 0.3 <= r < 0.7)
    l = sum(1 for r in rs if r < 0.3)
    n = len(rs)
    print(f"  {name.replace(chr(10), ' '):30}: H={h}/{n} M={m}/{n} L={l}/{n} ({100*l/n:.0f}% LOW)")
