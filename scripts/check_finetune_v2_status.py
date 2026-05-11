"""Check v2 fine-tune status."""
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
job_info = json.loads((ROOT / "data/finetune_v2/job_info.json").read_text(encoding="utf-8"))
job_id = job_info["job_id"]

job = client.fine_tuning.jobs.retrieve(job_id)
print(f"Job:    {job_id}")
print(f"Status: {job.status}")
print(f"Model:  {job.model} -> {job.fine_tuned_model or '(in progress)'}")
print(f"Trained tokens: {job.trained_tokens or 'N/A'}")

events = client.fine_tuning.jobs.list_events(fine_tuning_job_id=job_id, limit=12)
print("\nRecent events:")
for ev in events.data[:12]:
    print(f"  [{ev.level}] {ev.message}")

if job.status == "succeeded":
    job_info["fine_tuned_model"] = job.fine_tuned_model
    job_info["status"] = "succeeded"
    job_info["trained_tokens"] = job.trained_tokens
    (ROOT / "data/finetune_v2/job_info.json").write_text(
        json.dumps(job_info, indent=2), encoding="utf-8")
    print(f"\n*** SUCCESS *** Model: {job.fine_tuned_model}")
