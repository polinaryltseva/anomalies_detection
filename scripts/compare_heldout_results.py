"""Side-by-side comparison of FT v2 vs FT v3a on 20 held-out lots.

Output:
- data/eval/heldout_comparison.md (markdown for manual verification)
- data/eval/heldout_comparison_summary.json (counts)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOTS = json.loads((ROOT / "data/eval/heldout_v3_lots.json").read_text(encoding="utf-8"))["lots"]

DIRS = {
    "FT_v2": ROOT / "data/reports/heldout_ftv2",
    "FT_v3a": ROOT / "data/reports/heldout_ftv3a",
    "FT_v3a_mini": ROOT / "data/reports/heldout_ftv3a_mini",
}

OUT_MD = ROOT / "data/eval/heldout_comparison.md"
OUT_JSON = ROOT / "data/eval/heldout_comparison_summary.json"


def load_flags(model_dir: Path, lot_id: str) -> list[dict]:
    p = model_dir / f"{lot_id}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("flags", [])


def main() -> None:
    by_lot = {lot: {m: load_flags(d, lot) for m, d in DIRS.items()} for lot in LOTS}

    # Per-model totals
    totals = {m: 0 for m in DIRS}
    by_label = {m: Counter() for m in DIRS}
    by_lot_count = {m: 0 for m in DIRS}  # lots with at least one flag

    for lot, by_model in by_lot.items():
        for m, flags in by_model.items():
            totals[m] += len(flags)
            for f in flags:
                by_label[m][f["label"]] += 1
            if flags:
                by_lot_count[m] += 1

    # Build markdown
    lines = [
        "# FT v2 vs FT v3a — Held-out comparison (20 lots)",
        "",
        "## Summary",
        "",
        f"| Model | Total flags | Lots with flags | Avg per lot |",
        f"|---|---|---|---|",
    ]
    for m in DIRS:
        avg = totals[m] / 20
        lines.append(f"| {m} | {totals[m]} | {by_lot_count[m]}/20 | {avg:.1f} |")
    lines.append("")

    lines.append("## By label (count of flag instances)")
    lines.append("")
    all_labels = sorted(set().union(*(by_label[m].keys() for m in DIRS)))
    header_row = "| Label |"
    sep_row = "|---|"
    for m in DIRS:
        header_row += f" {m} |"
        sep_row += "---|"
    lines.append(header_row)
    lines.append(sep_row)
    for lbl in all_labels:
        row = f"| {lbl} |"
        for m in DIRS:
            row += f" {by_label[m].get(lbl, 0)} |"
        lines.append(row)
    lines.append("")

    lines.append("## Per-lot breakdown")
    lines.append("")

    for lot in LOTS:
        per_model_flags = {m: by_lot[lot][m] for m in DIRS}
        lines.append(f"### Lot {lot}")
        lines.append("")
        for m in DIRS:
            lines.append(f"- **{m}**: {len(per_model_flags[m])} flags")
        lines.append("")
        any_flags = any(per_model_flags[m] for m in DIRS)
        if any_flags:
            for m in DIRS:
                lines.append(f"**{m} flags**:")
                if per_model_flags[m]:
                    for f in per_model_flags[m]:
                        span = f["span_text"][:200].replace("\n", " ")
                        lines.append(f"- [{f['label']}] sec={f.get('section', '?')}, conf={f.get('confidence', '?')}: «{span}»")
                else:
                    lines.append("- _(none)_")
                lines.append("")
        else:
            lines.append("_(all models: no flags)_")
        lines.append("")
        lines.append("---")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "totals": totals,
        "by_label": {m: dict(c) for m, c in by_label.items()},
        "lots_with_flags": by_lot_count,
        "n_lots": len(LOTS),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== Summary ===")
    for m in DIRS:
        print(f"{m}: {totals[m]} flags across {by_lot_count[m]}/20 lots")
    print()
    print("By label:")
    header = f"{'Label':<40s}"
    for m in DIRS:
        header += f" {m:>12s}"
    print(header)
    for lbl in all_labels:
        row = f"  {lbl:<38s}"
        for m in DIRS:
            row += f" {by_label[m].get(lbl, 0):>12d}"
        print(row)
    print()
    print(f"\nWritten:\n  {OUT_MD}\n  {OUT_JSON}")


if __name__ == "__main__":
    main()
