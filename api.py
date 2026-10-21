from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from pipeline.config import DEFAULT_PROFILE, estimate_job_cost, get_profile, profile_to_dict
from storage.jobs import create_job, get_job, init_db
from worker import run_job
from urllib.parse import unquote

BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = Path(os.environ.get("SCREENTOSOP_JOBS_DIR", BASE_DIR / "jobs")).resolve()
DB_PATH = Path(os.environ.get("SCREENTOSOP_DB_PATH", BASE_DIR / "storage" / "jobs.sqlite3")).resolve()
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

app = FastAPI(title="ScreenToSOP API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _safe_job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    path = (JOBS_DIR / job_id).resolve()
    if path.parent != JOBS_DIR:
        raise HTTPException(status_code=404, detail="Job not found")
    return path


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ScreenToSOP"}


@app.post("/record-to-sop")
def record_to_sop(
    video: UploadFile = File(..., description="Screen recording video"),
    process_name: str = Form(default=""),
    target_audience: str = Form(default="New employee"),
    department_notes: str = Form(default=""),
    quality_profile: str = Form(default=DEFAULT_PROFILE),
) -> dict[str, Any]:
    filename = Path(video.filename or "recording.mp4").name
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported video format. Upload MP4, MOV, M4V, WEBM, MKV, or AVI.")

    content = video.file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded video is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Video exceeds the 250 MiB upload limit.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    input_path = job_dir / "input.mp4"
    input_path.write_bytes(content)
    profile = get_profile(quality_profile)
    metadata = {
        "filename": filename,
        "upload_name": filename,
        "process_name": process_name.strip(),
        "process_name_source": "user" if process_name.strip() else "derived",
        "target_audience": target_audience.strip() or "New employee",
        "department_notes": department_notes.strip(),
        "quality_profile": profile_to_dict(profile),
        "cost_estimate": estimate_job_cost(profile),
        "requested_generation_mode": "api_upload",
    }
    init_db(DB_PATH)
    create_job(DB_PATH, job_id, str(input_path), meta=metadata)
    try:
        run_job(job_id, job_dir, DB_PATH)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SOP processing failed: {type(exc).__name__}") from exc

    job = get_job(DB_PATH, job_id) or {}
    if job.get("status") != "complete":
        raise HTTPException(status_code=500, detail=job.get("error") or job.get("message") or "SOP processing failed")
    workflow_path = job_dir / "artifacts" / "workflow.json"
    workflow: dict[str, Any] = {}
    if workflow_path.is_file():
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            workflow = {}
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "process_name": workflow.get("process_name") or metadata["process_name"] or Path(filename).stem,
        "readiness": workflow.get("readiness", job.get("meta", {}).get("readiness", "needs_review")),
        "generation_mode": workflow.get("generation_mode", job.get("meta", {}).get("generation_mode", "unknown")),
        "steps": workflow.get("steps", []),
        "warnings": workflow.get("warnings", []),
        "artifacts": {
            "docx": f"/jobs/{job_id}/sop.docx",
            "markdown": f"/jobs/{job_id}/sop.md",
            "workflow_json": f"/jobs/{job_id}/workflow.json",
        },
    }

@app.get("/jobs/{job_id}/screenshots/{image_path:path}")
def get_job_screenshot(job_id: str, image_path: str):
    job_dir = _safe_job_dir(job_id)

    relative_path = Path(unquote(image_path))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    path = (job_dir / relative_path).resolve()

    if not path.is_relative_to(job_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(path.suffix.lower())

    if not media_type:
        raise HTTPException(status_code=404, detail="Unsupported screenshot format")

    return FileResponse(path, media_type=media_type)

@app.get("/jobs/{job_id}/{artifact_name}")
def download_artifact(job_id: str, artifact_name: str):
    job_dir = _safe_job_dir(job_id)
    artifacts = {
        "sop.docx": (job_dir / "sop.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "sop.md": (job_dir / "sop.md", "text/markdown; charset=utf-8"),
        "workflow.json": (job_dir / "artifacts" / "workflow.json", "application/json"),
    }
    if artifact_name not in artifacts:
        raise HTTPException(status_code=404, detail="Artifact not found")
    path, media_type = artifacts[artifact_name]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, media_type=media_type, filename=artifact_name)
