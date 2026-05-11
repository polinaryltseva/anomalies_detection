"""Stratified sample 60-80 flags из v3+2stage output для второй волны manual review.

Стратегия:
- Берём только лоты NE in v1 training (held-out tender_ids)
- Stratified по labels (нужно diverse coverage)
- Приоритет на medium-risk lots (наиболее informative)
- Skip уже размеченные flag_ids
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

random.seed(123)
V3_DIR = ROOT / "data/reports/bulk_v3"
RAW = ROOT / "data/raw/bulk"
OUT_DIR = ROOT / "data/labeled"

CONTEXT = 600  # shorter than v1 to fit more in markdown


# Lots already in v1 training data
existing_ann = [json.loads(l) for l in
                (OUT_DIR / "bulk_flag_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
already_annotated_lots = {a["tender_id"] for a in existing_ann}
already_annotated_flag_ids = {a["flag_id"] for a in existing_ann}

ens_ann = [json.loads(l) for l in
           (OUT_DIR / "ensemble_annotations.jsonl").read_text(encoding="utf-8").splitlines()]
for a in ens_ann:
    already_annotated_lots.add(a["tender_id"])

print(f"Already annotated tender_ids: {len(already_annotated_lots)}")

# Bottom-10 lots also in training data (negative examples)
bottom_10 = {'169629544', '169596415', '169608004', '169633366', '169618156',
             '169608015', '169633302', '169618157', '169625477', '169629441'}
training_lots = already_annotated_lots | bottom_10
print(f"All training lots: {len(training_lots)}")

# Find held-out tender_ids
held_out_lots = []
for p in sorted(V3_DIR.glob("*.json")):
    if p.name == "_summary.json":
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    if r["tender_id"] not in training_lots and r.get("flags"):
        held_out_lots.append(r)

print(f"Held-out lots with flags: {len(held_out_lots)}")


def flag_id(tender_id: str, label: str, span: str) -> str:
    return md5(f"{tender_id}|{label}|{span[:200]}".encode()).hexdigest()[:16]


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


# Stratified sample: ensure diverse label coverage
flags_by_label = defaultdict(list)
for r in held_out_lots:
    for f in r["flags"]:
        if flag_id(r["tender_id"], f["label"], f["span_text"]) in already_annotated_flag_ids:
            continue
        flags_by_label[f["label"]].append({
            "tender_id": r["tender_id"],
            "lot_risk": r["overall_risk_score"],
            "label": f["label"],
            "section": f.get("section", ""),
            "span_text": f["span_text"],
            "confidence": f.get("confidence", 0.0),
            "rationale": f.get("rationale", ""),
            "regulatory_reference": f.get("regulatory_reference", ""),
        })

print(f"\nFlags by label (held-out, not yet annotated):")
for lbl, fs in sorted(flags_by_label.items()):
    print(f"  {lbl}: {len(fs)}")

# Sample strategy: take up to N per label, prefer medium-risk lots
PER_LABEL_TARGET = 10
sample = []
for label, flags in flags_by_label.items():
    # Shuffle, then sort by risk preference: medium-risk first
    random.shuffle(flags)
    flags.sort(key=lambda f: abs(f["lot_risk"] - 0.6))  # closer to 0.6 = more interesting
    sample.extend(flags[:PER_LABEL_TARGET])

random.shuffle(sample)
sample = sample[:80]  # cap at 80
print(f"\nSampled: {len(sample)} flags")
print(f"By label: {dict(Counter(f['label'] for f in sample))}")
print(f"Unique lots: {len(set(f['tender_id'] for f in sample))}")

# Build markdown review pack
lines = [
    f"# v2 Review Pack — {len(sample)} flags",
    "",
    "Held-out lots (not in v1 training). Stratified by label.",
    "",
    "Format: TRUE / PARTIAL / FALSE for each flag.",
    "",
    "---",
    "",
]
out_records = []
for i, f in enumerate(sample, 1):
    fid = flag_id(f["tender_id"], f["label"], f["span_text"])
    full = lot_text(f["tender_id"])
    before, match, after = find_context(full, f["span_text"])

    lines.append(f"## #{i} [{f['label']}] — {f['tender_id']}")
    lines.append("")
    lines.append(f"- **flag_id**: `{fid}`")
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

    out_records.append({**f, "flag_id": fid, "n": i})

(OUT_DIR / "v2_review_pack.md").write_text("\n".join(lines), encoding="utf-8")
(OUT_DIR / "v2_review_pack.json").write_text(
    json.dumps(out_records, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"\nSaved:")
print(f"  data/labeled/v2_review_pack.md  ({(OUT_DIR/'v2_review_pack.md').stat().st_size//1024} KB)")
print(f"  data/labeled/v2_review_pack.json")
