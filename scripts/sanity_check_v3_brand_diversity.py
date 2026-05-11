"""Check brand_or_model_targeting flag diversity in v3 dataset."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data/finetune_v3"


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def assistant_flags(ex: dict) -> list[dict]:
    asst = next(m for m in ex["messages"] if m["role"] == "assistant")["content"]
    try:
        return json.loads(asst).get("flags", [])
    except json.JSONDecodeError:
        return []


def main() -> None:
    train = load(DIR / "training.jsonl")

    brand_spans = []
    for ex in train:
        for f in assistant_flags(ex):
            if f["label"] == "brand_or_model_targeting":
                brand_spans.append(f["span_text"])

    print(f"Total brand_or_model_targeting flags: {len(brand_spans)}")
    print()

    # Group by template patterns
    pat_no_equiv = re.compile(r"эквивалент\s+не\s+допу", re.IGNORECASE)
    pat_brand_word = re.compile(r"\b[A-Z][a-zA-Z]+", re.UNICODE)

    no_equiv_count = sum(1 for s in brand_spans if pat_no_equiv.search(s))
    has_latin_brand = sum(1 for s in brand_spans if pat_brand_word.search(s))
    print(f"Spans with «эквивалент не допустима»: {no_equiv_count}")
    print(f"Spans with Latin brand-like words: {has_latin_brand}")
    print()

    # Show length distribution
    lengths = [len(s) for s in brand_spans]
    short = sum(1 for l in lengths if l < 50)
    medium = sum(1 for l in lengths if 50 <= l < 150)
    long_ = sum(1 for l in lengths if l >= 150)
    print(f"Length: short<50: {short}, 50-150: {medium}, >=150: {long_}")
    print()

    # Sample 10 unique-ish spans
    print("Sample 15 brand spans (first 100 chars):")
    seen_prefixes = set()
    samples = []
    for s in brand_spans:
        prefix = s[:30]
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        samples.append(s)
        if len(samples) >= 15:
            break
    for i, s in enumerate(samples, 1):
        print(f"  {i}. «{s[:120]}»")

    # Group by «container» patterns
    print("\nDuplicates analysis (top 20 most common spans):")
    span_count = Counter(brand_spans)
    for span, n in span_count.most_common(20):
        if n > 1:
            print(f"  {n}x : «{span[:100]}»")


if __name__ == "__main__":
    main()
