"""Grinder Router - Handles file processing for challenge generation."""

import os
import uuid
import asyncio
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlmodel import Session

from config import get_settings
from database import engine
from services.grinder import process_file_with_job
from models.import_job import ImportJob

router = APIRouter()

logger = logging.getLogger(__name__)
settings = get_settings()

UPLOAD_DIR = os.path.abspath(settings.GRINDER_UPLOAD_DIR)
ALLOWED_EXTENSIONS = {".pdf", ".pptx"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

os.makedirs(UPLOAD_DIR, exist_ok=True)


class ProcessRequest(BaseModel):
    file_path: str


class CreateJobResponse(BaseModel):
    success: bool
    job_id: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress_percent: int
    course_id: str | None
    topics_count: int
    challenges_count: int
    error_message: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


@router.post("/jobs")
async def create_import_job(file: UploadFile = File(...)) -> CreateJobResponse:
    """Upload a file and create an import job to process it asynchronously.
    
    Returns immediately with a job_id that can be used to track progress.
    """
    try:
        filename = file.filename or ""
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type '{file_ext or 'unknown'}'. "
                    f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )

        # Save uploaded file
        file_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
            )
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Create job record
        job_id = str(uuid.uuid4())
        job = ImportJob(
            id=job_id,
            file_path=file_path,
            status="pending"
        )
        
        with Session(engine) as session:
            session.add(job)
            session.commit()
        
        # Start async processing
        task = asyncio.create_task(process_file_with_job(job_id, file_path, source_filename=filename))

        def _log_task_result(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except Exception as exc:
                logger.exception("Import job task failed job_id=%s: %s", job_id, exc)

        task.add_done_callback(_log_task_result)
        
        return CreateJobResponse(
            success=True,
            job_id=job_id,
            message="Job created successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get the status of an import job."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            
            return JobStatusResponse(
                id=job.id,
                status=job.status,
                progress_percent=job.progress_percent,
                course_id=job.course_id,
                topics_count=job.topics_count,
                challenges_count=job.challenges_count,
                error_message=job.error_message,
                created_at=job.created_at.isoformat() if job.created_at else "",
                updated_at=job.updated_at.isoformat() if job.updated_at else "",
                completed_at=job.completed_at.isoformat() if job.completed_at else None
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str) -> str:
    """Get the logs for an import job."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            
            logs = job.get_logs()
            return "\n".join(logs)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job logs: {str(e)}")


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict:
    """Cancel an import job (marks it as error)."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            
            if job.status in ["completed", "error"]:
                return {"success": False, "message": f"Job is already {job.status}"}
            
            job.status = "error"
            job.error_message = "Cancelled by user"
            session.commit()
            
            return {"success": True, "message": "Job cancelled"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")


@router.get("/status")
async def get_grinder_status():
    """Get the current grinder status (backwards compatibility)."""
    try:
        with Session(engine) as session:
            # Count active jobs
            from sqlmodel import select
            pending_count = len(session.exec(select(ImportJob).where(ImportJob.status == "pending")).all())
            processing_count = len(session.exec(select(ImportJob).where(ImportJob.status == "processing")).all())
            
            return {
                "status": "busy" if processing_count > 0 else "idle",
                "queue_length": pending_count,
                "active_jobs": processing_count,
                "max_concurrent": 3
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


# Legacy endpoints for backwards compatibility

@router.post("/process")
async def process_grinder_file(request: ProcessRequest):
    """Process a file to generate challenges (synchronous - deprecated)."""
    try:
        from services.grinder import process_file
        result = await process_file(request.file_path)
        return {
            "success": True,
            "message": "File processed successfully",
            "course_id": result.get("course_id"),
            "topics_count": result.get("topics_count", 0),
            "challenges_count": result.get("challenges_count", 0),
            "status": result.get("status"),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and process it to generate challenges (synchronous - deprecated).
    
    Use POST /jobs for async processing with progress tracking.
    """
    try:
        from services.grinder import process_file

        filename = file.filename or ""
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type '{file_ext or 'unknown'}'. "
                    f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )
        
        # Save uploaded file
        file_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
            )

        with open(file_path, "wb") as f:
            f.write(content)
        
        # Process the file
        result = await process_file(file_path, source_filename=filename)
        
        return {
            "success": True,
            "message": "File processed successfully",
            "course_id": result.get("course_id"),
            "topics_count": result.get("topics_count", 0),
            "challenges_count": result.get("challenges_count", 0),
            "status": result.get("status"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
