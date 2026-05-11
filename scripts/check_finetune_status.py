"""Check fine-tune job status and progress."""
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

job_info = json.loads((ROOT / "data/finetune/job_info.json").read_text(encoding="utf-8"))
job_id = job_info["job_id"]

job = client.fine_tuning.jobs.retrieve(job_id)
print(f"Job:    {job_id}")
print(f"Status: {job.status}")
print(f"Model:  {job.model} -> {job.fine_tuned_model or '(in progress)'}")
print(f"Trained tokens: {job.trained_tokens or 'N/A'}")
print(f"Error: {job.error}")

# Get last 10 events for progress
events = client.fine_tuning.jobs.list_events(fine_tuning_job_id=job_id, limit=15)
print(f"\nRecent events:")
for ev in events.data[:15]:
    print(f"  [{ev.level}] {ev.message}")

if job.status == "succeeded":
    # Save the fine-tuned model name for later use
    job_info["fine_tuned_model"] = job.fine_tuned_model
    job_info["status"] = "succeeded"
    job_info["trained_tokens"] = job.trained_tokens
    (ROOT / "data/finetune/job_info.json").write_text(json.dumps(job_info, indent=2), encoding="utf-8")
    print(f"\n*** SUCCESS *** Fine-tuned model: {job.fine_tuned_model}")
elif job.status in ("failed", "cancelled"):
    print(f"\n*** {job.status.upper()} ***")
