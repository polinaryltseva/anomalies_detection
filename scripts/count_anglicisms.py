# -*- coding: utf-8 -*-
"""Подсчёт оставшихся англицизмов только в строковых литералах."""
import io
import re
import tokenize
from collections import Counter
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "scripts/build_vkr.py"
text = src.read_text(encoding="utf-8")
tokens = list(tokenize.tokenize(io.BytesIO(text.encode("utf-8")).readline))

QUOTES = ('"""', "'''", '"', "'")
text_only = []
for tok in tokens:
    if tok.type != tokenize.STRING:
        continue
    s = tok.string
    # Strip prefix
    while s and s[0] in "rbfRBF":
        s = s[1:]
    # Strip quotes
    for q in QUOTES:
        if s.startswith(q) and s.endswith(q):
            text_only.append(s[len(q):-len(q)])
            break

combined = " ".join(text_only)
words = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b", combined)
counter = Counter(w.lower() for w in words)

print(f"Уникальных англицизмов в строковых литералах: {len(counter)}")
print(f"Всего вхождений: {sum(counter.values())}")
print()
print("Топ-40:")
for w, c in counter.most_common(40):
    if c >= 2:
        print(f"  {c:4d}  {w}")
