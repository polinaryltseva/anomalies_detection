"""Ensemble: intersection of v2+2stage AND v3+2stage flags.

Logic:
- A flag from v3 is "validated" if there's a fuzzy-matching flag in v2+2stage
  for the same lot+section with overlapping span (≥40 chars common substring).
- Output: ensemble report per lot with only validated flags.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from annotate_v2 import check_whitelist, find_context, lot_text  # noqa: E402

V2 = ROOT / "data/reports/bulk_v2_2stage"
V3 = ROOT / "data/reports/bulk_v3"
OUT = ROOT / "data/reports/bulk_ensemble"
OUT.mkdir(parents=True, exist_ok=True)


def load(d: Path) -> dict[str, dict]:
    out = {}
    for p in sorted(d.glob("*.json")):
        if p.name == "_summary.json":
            continue
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return out


def fuzzy_match(s1: str, s2: str, min_overlap: int = 40) -> bool:
    """True if s1 and s2 share a substring of length ≥ min_overlap."""
    if not s1 or not s2:
        return False
    if min_overlap > min(len(s1), len(s2)):
        min_overlap = min(len(s1), len(s2))
    # Quick check: shorter string mostly inside longer?
    short, long = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
    if short in long:
        return True
    # Overlap heuristic: common N-gram substring
    for i in range(0, len(short) - min_overlap + 1, 5):
        if short[i:i + min_overlap] in long:
            return True
    return False


def main() -> None:
    v2 = load(V2)
    v3 = load(V3)
    common = sorted(set(v2) & set(v3))
    print(f"Common lots: {len(common)}")

    summary = []
    total_v2_flags = 0
    total_v3_flags = 0
    total_ensemble_flags = 0
    high = med = low = 0

    for lot_id in common:
        v2_flags = v2[lot_id]["flags"]
        v3_flags = v3[lot_id]["flags"]
        total_v2_flags += len(v2_flags)
        total_v3_flags += len(v3_flags)

        # For each v3 flag, check if v2 has a matching one (same label + section + overlapping span)
        ensemble_flags = []
        for vf in v3_flags:
            for v2f in v2_flags:
                if (vf["label"] == v2f["label"]
                    and vf["section"] == v2f["section"]
                    and fuzzy_match(vf["span_text"], v2f["span_text"])):
                    # Take the higher-confidence version
                    chosen = vf if vf.get("confidence", 0) >= v2f.get("confidence", 0) else v2f
                    ensemble_flags.append(chosen)
                    break

        total_ensemble_flags += len(ensemble_flags)
        # Compute risk score
        sum_conf = sum(f.get("confidence", 0) for f in ensemble_flags)
        risk = round(1.0 - math.exp(-sum_conf), 3) if ensemble_flags else 0.0
        if risk >= 0.7:
            level = "high"
            high += 1
        elif risk >= 0.3:
            level = "medium"
            med += 1
        else:
            level = "low"
            low += 1

        report = {
            "tender_id": lot_id,
            "overall_risk_score": risk,
            "risk_level": level,
            "flags": ensemble_flags,
            "method": "ensemble:v2+2stage_AND_v3+2stage",
        }
        (OUT / f"{lot_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        summary.append({
            "tender_id": lot_id,
            "v2_flags": len(v2_flags),
            "v3_flags": len(v3_flags),
            "ensemble_flags": len(ensemble_flags),
            "risk": risk,
            "level": level,
        })

    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(common)
    print(f"\nv2+2stage:   total flags = {total_v2_flags}, avg = {total_v2_flags/n:.1f}")
    print(f"v3+2stage:   total flags = {total_v3_flags}, avg = {total_v3_flags/n:.1f}")
    print(f"Ensemble:    total flags = {total_ensemble_flags}, avg = {total_ensemble_flags/n:.1f}")
    print(f"\nEnsemble risk distribution: HIGH={high} MED={med} LOW={low}")
    print(f"\nSaved -> {OUT}")

    # Heuristic precision check
    n_ens = 0
    n_fw = 0
    for lot_id in common:
        full = lot_text(lot_id)
        rep = json.loads((OUT / f"{lot_id}.json").read_text(encoding="utf-8"))
        for f in rep["flags"]:
            n_ens += 1
            ctx = find_context(full, f["span_text"])
            wl, _ = check_whitelist(f["span_text"], ctx, f["label"])
            if wl:
                n_fw += 1
    if n_ens:
        fp_rate = n_fw / n_ens
        est_precision = max(0, 1 - fp_rate / 0.686)
        print(f"\nEnsemble heuristic FP rate: {fp_rate:.1%}")
        print(f"Estimated real precision: {est_precision:.1%}")


if __name__ == "__main__":
    main()
