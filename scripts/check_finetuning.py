"""Check which models support fine-tuning by attempting to create a job
and immediately cancelling. Just queries the API — does NOT incur costs."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Minimum valid fine-tuning training data: ≥10 examples
training = []
for i in range(10):
    training.append({
        "messages": [
            {"role": "system", "content": "Test."},
            {"role": "user", "content": f"Test message {i}"},
            {"role": "assistant", "content": "Test response"},
        ]
    })

# Write to temp jsonl
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
    for ex in training:
        f.write(json.dumps(ex) + "\n")
    tmp_path = f.name

print(f"Uploading test training file: {tmp_path}")
upload = client.files.create(
    file=open(tmp_path, "rb"),
    purpose="fine-tune",
)
print(f"  File id: {upload.id}")

# Try creating fine-tuning jobs for various models
test_models = [
    "gpt-4o-mini-2024-07-18",
    "gpt-4o-2024-08-06",
    "gpt-4.1-2025-04-14",
    "gpt-4.1-mini-2025-04-14",
    "gpt-4.1-nano-2025-04-14",
    "gpt-5-2025-08-07",
    "gpt-5-mini-2025-08-07",
    "gpt-5.1-2025-11-13",
    "gpt-5.4-2026-03-05",
    "gpt-5.4-mini-2026-03-17",
    "gpt-5.5-2026-04-23",
]

results = {}
for model in test_models:
    try:
        job = client.fine_tuning.jobs.create(
            training_file=upload.id,
            model=model,
        )
        # Immediately cancel to avoid running
        client.fine_tuning.jobs.cancel(job.id)
        results[model] = "SUPPORTED"
        print(f"  [{model}] SUPPORTED (job {job.id} cancelled)")
    except Exception as e:
        msg = str(e)
        if "model" in msg.lower() and ("not" in msg.lower() or "invalid" in msg.lower() or "support" in msg.lower()):
            results[model] = "NOT supported"
            print(f"  [{model}] NOT supported: {msg[:120]}")
        else:
            results[model] = f"ERROR: {msg[:120]}"
            print(f"  [{model}] ERROR: {msg[:120]}")

# Cleanup test file
try:
    client.files.delete(upload.id)
    print(f"\nDeleted test file {upload.id}")
except Exception:
    pass

print("\n=== SUMMARY ===")
for m, r in results.items():
    print(f"  {m}: {r}")
