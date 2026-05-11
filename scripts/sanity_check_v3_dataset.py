"""Sanity checks on FT v3 training/validation dataset before launching SFT job."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data/finetune_v3"


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def tender_id(ex: dict) -> str:
    user = next(m for m in ex["messages"] if m["role"] == "user")["content"]
    m = re.search(r"Tender ID: (\d+)", user)
    return m.group(1) if m else ""


def section(ex: dict) -> str:
    user = next(m for m in ex["messages"] if m["role"] == "user")["content"]
    m = re.search(r"Section: (\S+)", user)
    return m.group(1) if m else ""


def assistant_flags(ex: dict) -> list[dict]:
    asst = next(m for m in ex["messages"] if m["role"] == "assistant")["content"]
    try:
        return json.loads(asst).get("flags", [])
    except json.JSONDecodeError:
        return []


def chars(ex: dict, role: str) -> int:
    return len(next(m for m in ex["messages"] if m["role"] == role)["content"])


def main() -> None:
    train = load(DIR / "training.jsonl")
    val = load(DIR / "validation.jsonl")

    print(f"Loaded train={len(train)}, val={len(val)}")
    print("=" * 70)

    # CHECK 1 — Leakage by tender_id
    print("\n[1] Leakage check (tender_id appears in BOTH train and val):")
    train_tids = {tender_id(ex) for ex in train}
    val_tids = {tender_id(ex) for ex in val}
    overlap = train_tids & val_tids
    print(f"  train tenders: {len(train_tids)}")
    print(f"  val tenders:   {len(val_tids)}")
    print(f"  overlap:       {len(overlap)} {'[FAIL] LEAK' if overlap else '[OK] clean'}")
    if overlap:
        print(f"  leaked tenders: {sorted(overlap)[:10]}")

    # CHECK 2 — Positive distribution by label
    print("\n[2] Label distribution in TRUE/PARTIAL flags (kept_flags):")
    label_count = Counter()
    pos_train = 0
    neg_train = 0
    for ex in train:
        flags = assistant_flags(ex)
        if flags:
            pos_train += 1
            for f in flags:
                label_count[f["label"]] += 1
        else:
            neg_train += 1
    print(f"  Train positives: {pos_train}, negatives: {neg_train}")
    print(f"  Total flag instances in train: {sum(label_count.values())}")
    for lbl, n in label_count.most_common():
        bar = "#" * int(n / max(label_count.values()) * 30)
        print(f"  {lbl:35s} {n:4d}  {bar}")

    # CHECK 3 — Length sanity
    print("\n[3] Length statistics (chars):")
    user_lens = [chars(ex, "user") for ex in train]
    asst_lens = [chars(ex, "assistant") for ex in train]
    print(f"  User msg:      mean={mean(user_lens):.0f}  median={median(user_lens):.0f}  max={max(user_lens)}  min={min(user_lens)}")
    print(f"  Assistant msg: mean={mean(asst_lens):.0f}  median={median(asst_lens):.0f}  max={max(asst_lens)}")

    # Check user_msg truncation: section text limited to 4000 chars
    truncated = sum(1 for ex in train if chars(ex, "user") > 4500)  # 4000 + prompt overhead
    print(f"  Examples likely with >=4000-char section text: {truncated}/{len(train)} ({100*truncated/len(train):.0f}%)")

    # CHECK 4 — Section distribution
    print("\n[4] Section distribution (positive examples):")
    sec_count = Counter()
    for ex in train:
        if assistant_flags(ex):
            sec_count[section(ex)] += 1
    for sec, n in sec_count.most_common():
        print(f"  {sec:20s} {n}")

    # CHECK 5 — Sample 3 random positives & 3 negatives for visual review
    print("\n[5] Sample examples for visual sanity:")
    import random
    random.seed(42)
    pos_examples = [ex for ex in train if assistant_flags(ex)]
    neg_examples = [ex for ex in train if not assistant_flags(ex)]
    print(f"\n  --- 2 random POSITIVE examples ---")
    for i, ex in enumerate(random.sample(pos_examples, min(2, len(pos_examples))), 1):
        tid = tender_id(ex)
        sec = section(ex)
        flags = assistant_flags(ex)
        print(f"\n  [POS #{i}] tender={tid} section={sec}, {len(flags)} flag(s):")
        for f in flags:
            span = f["span_text"][:100]
            print(f"    - [{f['label']}] «{span}»")
    print(f"\n  --- 2 random NEGATIVE examples ---")
    for i, ex in enumerate(random.sample(neg_examples, min(2, len(neg_examples))), 1):
        tid = tender_id(ex)
        sec = section(ex)
        # Show first 200 chars of section text
        user = next(m for m in ex["messages"] if m["role"] == "user")["content"]
        snippet = user.split("Текст секции:\n---\n")[1][:200] if "Текст секции:" in user else user[:200]
        print(f"\n  [NEG #{i}] tender={tid} section={sec}")
        print(f"    Snippet: {snippet[:150].strip()}...")

    # CHECK 6 — Verdict distribution by source (within positives)
    print("\n[6] R1-only check (avoid 90% «Не предусмотрено» domination):")
    r1_pattern = re.compile(r"не\s+(предусмотрен|установлен|применя)", re.IGNORECASE)
    r1_count = 0
    other_count = 0
    for ex in train:
        for f in assistant_flags(ex):
            if r1_pattern.search(f["span_text"]):
                r1_count += 1
            else:
                other_count += 1
    total = r1_count + other_count
    if total > 0:
        print(f"  R1 «Не предусмотрено/установлен/применя» pattern: {r1_count}/{total} ({100*r1_count/total:.0f}%)")
        print(f"  Other patterns: {other_count}/{total} ({100*other_count/total:.0f}%)")
        if r1_count > 0.7 * total:
            print(f"  [WARN]  R1 dominance > 70% — модель будет смещена к этому паттерну")
        else:
            print(f"  [OK]  R1 не доминирует, разнообразие OK")


if __name__ == "__main__":
    main()
