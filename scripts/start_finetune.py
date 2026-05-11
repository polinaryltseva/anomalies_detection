"""Upload training/validation files and create fine-tune job for gpt-4.1."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

train_path = ROOT / "data/finetune/training.jsonl"
val_path = ROOT / "data/finetune/validation.jsonl"
print(f"Training file: {train_path} ({train_path.stat().st_size//1024} KB)")
print(f"Validation file: {val_path} ({val_path.stat().st_size//1024} KB)")

# Upload training file
print("\nUploading training file...")
train_upload = client.files.create(
    file=open(train_path, "rb"),
    purpose="fine-tune",
)
print(f"  Train file ID: {train_upload.id}")

# Upload validation file
print("\nUploading validation file...")
val_upload = client.files.create(
    file=open(val_path, "rb"),
    purpose="fine-tune",
)
print(f"  Val file ID: {val_upload.id}")

# Create fine-tune job — gpt-4.1
print("\nCreating fine-tune job for gpt-4.1...")
job = client.fine_tuning.jobs.create(
    training_file=train_upload.id,
    validation_file=val_upload.id,
    model="gpt-4.1-2025-04-14",
    suffix="tender-anomaly-v1",
    hyperparameters={
        "n_epochs": 3,  # Default for small dataset
    },
)

print(f"\nJob created: {job.id}")
print(f"Status: {job.status}")
print(f"Model: {job.model}")

# Save job info for later retrieval
job_info = {
    "job_id": job.id,
    "model_base": "gpt-4.1-2025-04-14",
    "training_file_id": train_upload.id,
    "validation_file_id": val_upload.id,
    "created_at": job.created_at,
    "status": job.status,
}
(ROOT / "data/finetune/job_info.json").write_text(json.dumps(job_info, indent=2), encoding="utf-8")

print(f"\nSaved job info -> data/finetune/job_info.json")
print(f"\nMonitor with: python scripts/check_finetune_status.py")
