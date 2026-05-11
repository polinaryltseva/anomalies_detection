"""Phase 2: Build v3 review pack — стратифицированная выборка флагов из
существующих v3+2s outputs (на 396 лотах, без новых API запусков).

Стратегия: фокус на паттернах где FT v2 слабая.
Источник: data/reports/bulk_v3/<lot>.json (уже посчитано).

Целевая выборка ~150 флагов:
- 30: brand_or_model_targeting в section=pricing/tz (Adventurer Pro-style)
- 25: unusual_contract_terms (extreme payment terms)
- 25: conflict_of_interest_signals (ФИО)
- 20: restrictive_tech_specs (narrow tech specs)
- 30: hard negatives — flags на лотах которые v1 пометил FALSE manually
- 20: diverse FALSE — стандартные нормы для balance

Skip flag_ids уже размеченные в bulk_flag_annotations или v2_flag_annotations.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from hashlib import md5
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tender_anomaly.parse.extractor import extract  # noqa: E402

random.seed(42)
V3_DIR = ROOT / "data/reports/bulk_v3"
RAW = ROOT / "data/raw/bulk"
OUT_DIR = ROOT / "data/labeled"
CONTEXT = 600


def flag_id(tender_id: str, label: str, span: str) -> str:
    return md5(f"{tender_id}|{label}|{span[:200]}".encode()).hexdigest()[:16]


# Skip уже размеченные flag_ids
existing_ann = []
for path in [
    ROOT / "data/labeled/bulk_flag_annotations.jsonl",
    ROOT / "data/labeled/v2_flag_annotations.jsonl",
    ROOT / "data/labeled/ensemble_annotations.jsonl",
    ROOT / "data/labeled/gpt55_annotations.jsonl",
]:
    if path.exists():
        for l in path.read_text(encoding="utf-8").splitlines():
            if l.strip():
                existing_ann.append(json.loads(l))

annotated_flag_ids = {a["flag_id"] for a in existing_ann if "flag_id" in a}
annotated_lots = {a["tender_id"] for a in existing_ann}
print(f"Already annotated: {len(annotated_flag_ids)} flag_ids across {len(annotated_lots)} lots")

# Загружаем v3+2s reports
all_flags = []
for p in sorted(V3_DIR.glob("*.json")):
    if p.name == "_summary.json":
        continue
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    for f in r.get("flags", []):
        fid = flag_id(r["tender_id"], f["label"], f["span_text"])
        if fid in annotated_flag_ids:
            continue
        all_flags.append({
            "flag_id": fid,
            "tender_id": r["tender_id"],
            "lot_risk": r["overall_risk_score"],
            "label": f["label"],
            "section": f.get("section", ""),
            "span_text": f["span_text"],
            "confidence": f.get("confidence", 0.0),
            "rationale": f.get("rationale", ""),
            "regulatory_reference": f.get("regulatory_reference", ""),
        })

print(f"\nTotal v3+2s flags (excluding annotated): {len(all_flags)}")
by_label = Counter(f["label"] for f in all_flags)
print("By label:")
for lbl, n in by_label.most_common():
    print(f"  {lbl}: {n}")


# Стратифицированная выборка по таргетам
def sample_filter(predicate, n_target: int, all_pool: list[dict]) -> list[dict]:
    """Random sample N flags matching predicate, prefer medium-risk lots."""
    pool = [f for f in all_pool if predicate(f)]
    random.shuffle(pool)
    pool.sort(key=lambda f: abs(f["lot_risk"] - 0.6))
    return pool[:n_target]


# Категории
sample = []
seen_fids = set()


def add(flags, category):
    nonlocal_added = []
    for f in flags:
        if f["flag_id"] in seen_fids:
            continue
        seen_fids.add(f["flag_id"])
        nonlocal_added.append({**f, "_category": category})
    return nonlocal_added


# 1. Brand+model в pricing/tz (Adventurer Pro style)
sel = sample_filter(
    lambda f: f["label"] == "brand_or_model_targeting" and f["section"] in ("pricing", "tz"),
    35, all_flags,
)
sample.extend(add(sel, "brand_pricing"))
print(f"\n1. brand_or_model_targeting in pricing/tz: {len(sel)} sampled")

# 2. Extreme contract terms
sel = sample_filter(
    lambda f: f["label"] == "unusual_contract_terms",
    25, all_flags,
)
sample.extend(add(sel, "contract_terms"))
print(f"2. unusual_contract_terms: {len(sel)} sampled")

# 3. ФИО / COI signals
sel = sample_filter(
    lambda f: f["label"] == "conflict_of_interest_signals",
    25, all_flags,
)
sample.extend(add(sel, "coi"))
print(f"3. conflict_of_interest_signals: {len(sel)} sampled")

# 4. Narrow tech specs
sel = sample_filter(
    lambda f: f["label"] == "restrictive_tech_specs" and f["section"] == "tz",
    20, all_flags,
)
sample.extend(add(sel, "tech_specs"))
print(f"4. restrictive_tech_specs in tz: {len(sel)} sampled")

# 5. Hard negatives — short_deadlines/disprop_qual/documentary which are usually FALSE
sel = sample_filter(
    lambda f: f["label"] in ("unusual_short_deadlines", "disproportionate_qualification", "documentary_burden"),
    30, all_flags,
)
sample.extend(add(sel, "hard_negative_or_diverse"))
print(f"5. hard negatives candidates (short_deadlines/disprop/docs): {len(sel)} sampled")

# 6. ambiguous_evaluation_criteria — diverse cases (not just R1 «не предусмотрено»)
sel = sample_filter(
    lambda f: f["label"] == "ambiguous_evaluation_criteria",
    15, all_flags,
)
sample.extend(add(sel, "eval_criteria"))
print(f"6. ambiguous_evaluation_criteria: {len(sel)} sampled")

random.shuffle(sample)
print(f"\nTotal sampled: {len(sample)}")
print(f"By category: {Counter(f['_category'] for f in sample)}")


# Build markdown for manual review
_text_cache = {}

def lot_text(lot_id: str) -> str:
    if lot_id in _text_cache:
        return _text_cache[lot_id]
    d = RAW / lot_id
    if not d.exists():
        _text_cache[lot_id] = ""
        return ""
    parts = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in {".docx", ".pdf", ".rtf", ".xlsx", ".xls", ".odt"}:
            continue
        ed = extract(f)
        if ed.text:
            parts.append(ed.text)
    text = "\n\n".join(parts)
    _text_cache[lot_id] = text
    return text


def find_context(text: str, span: str) -> tuple[str, str, str]:
    if not text or not span:
        return "", span, ""
    idx = text.find(span)
    if idx < 0:
        norm_text = re.sub(r"\s+", " ", text)
        norm_span = re.sub(r"\s+", " ", span)
        idx = norm_text.find(norm_span)
        if idx < 0:
            return "", span, ""
        text = norm_text
    s = max(0, idx - CONTEXT)
    e = min(len(text), idx + len(span) + CONTEXT)
    return text[s:idx], text[idx:idx + len(span)], text[idx + len(span):e]


lines = [
    f"# v3 Review Pack — {len(sample)} flags",
    "",
    "Phase 2 of FT v3 plan: stratified sample focused on patterns where FT v2 weak.",
    "",
    f"Categories: {dict(Counter(f['_category'] for f in sample))}",
    "",
    "---",
    "",
]

for i, f in enumerate(sample, 1):
    full = lot_text(f["tender_id"])
    before, match, after = find_context(full, f["span_text"])

    lines.append(f"## #{i} [{f['label']}] — {f['tender_id']} ({f['_category']})")
    lines.append("")
    lines.append(f"- **flag_id**: `{f['flag_id']}`")
    lines.append(f"- **lot_risk**: {f['lot_risk']:.2f}")
    lines.append(f"- **section**: {f['section']}")
    lines.append(f"- **conf**: {f['confidence']}")
    lines.append(f"- **rationale**: {f['rationale']}")
    lines.append("")
    lines.append("### Span:")
    lines.append(f"> «{f['span_text']}»")
    lines.append("")
    lines.append("### Context:")
    lines.append("```")
    lines.append(f"{before}【{match}】{after}")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")


(OUT_DIR / "v3_review_pack.md").write_text("\n".join(lines), encoding="utf-8")
(OUT_DIR / "v3_review_pack.json").write_text(
    json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"\nSaved:")
print(f"  data/labeled/v3_review_pack.md  ({(OUT_DIR/'v3_review_pack.md').stat().st_size//1024} KB)")
print(f"  data/labeled/v3_review_pack.json")
