"""Launch v2 fine-tune on gpt-4.1 with balanced 204-example dataset."""
from __future__ import annotations

import json
import os
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

train_path = ROOT / "data/finetune_v2/training.jsonl"
val_path = ROOT / "data/finetune_v2/validation.jsonl"

print(f"Train: {train_path} ({train_path.stat().st_size//1024} KB)")
print(f"Val:   {val_path} ({val_path.stat().st_size//1024} KB)")

print("\nUploading training file...")
train_upload = client.files.create(file=open(train_path, "rb"), purpose="fine-tune")
print(f"  Train file ID: {train_upload.id}")

print("Uploading validation file...")
val_upload = client.files.create(file=open(val_path, "rb"), purpose="fine-tune")
print(f"  Val file ID: {val_upload.id}")

print("\nCreating fine-tune job v2 (gpt-4.1, 5 epochs)...")
job = client.fine_tuning.jobs.create(
    training_file=train_upload.id,
    validation_file=val_upload.id,
    model="gpt-4.1-2025-04-14",
    suffix="tender-anomaly-v2",
    hyperparameters={"n_epochs": 5},
)

print(f"\nJob: {job.id}")
print(f"Status: {job.status}")

job_info = {
    "job_id": job.id,
    "model_base": "gpt-4.1-2025-04-14",
    "training_file_id": train_upload.id,
    "validation_file_id": val_upload.id,
    "created_at": job.created_at,
    "status": job.status,
    "version": "v2",
    "n_epochs": 5,
    "n_train": 184,
    "n_val": 20,
}
(ROOT / "data/finetune_v2/job_info.json").write_text(
    json.dumps(job_info, indent=2), encoding="utf-8")

print(f"\nSaved -> data/finetune_v2/job_info.json")
print(f"Monitor: python scripts/check_finetune_v2_status.py")
