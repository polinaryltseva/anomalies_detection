"""Check FT v3 job status."""
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

job_info = json.loads((ROOT / "data/finetune_v3/job_info.json").read_text(encoding="utf-8"))
job = client.fine_tuning.jobs.retrieve(job_info["job_id"])

print(f"Job: {job.id}")
print(f"Status: {job.status}")
if job.fine_tuned_model:
    print(f"Model: {job.fine_tuned_model}")
if job.trained_tokens:
    print(f"Trained tokens: {job.trained_tokens}")
    print(f"Cost: ~${job.trained_tokens * 25 / 1_000_000:.2f}")
if job.error:
    print(f"Error: {job.error}")
if hasattr(job, 'estimated_finish') and job.estimated_finish:
    import datetime as dt
    eta = dt.datetime.fromtimestamp(job.estimated_finish)
    print(f"ETA: {eta}")

# Update job_info with current status
job_info["status"] = job.status
if job.fine_tuned_model:
    job_info["fine_tuned_model"] = job.fine_tuned_model
if job.trained_tokens:
    job_info["trained_tokens"] = job.trained_tokens
(ROOT / "data/finetune_v3/job_info.json").write_text(
    json.dumps(job_info, indent=2), encoding="utf-8"
)
