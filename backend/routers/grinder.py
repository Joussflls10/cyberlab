"""Grinder Router - Handles file processing for challenge generation."""

import os
import uuid
import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlmodel import Session, select

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
VALID_JOB_STATUSES = {"pending", "processing", "completed", "error"}
TERMINAL_JOB_STATUSES = {"completed", "error"}


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
    retriable: bool
    course_id: str | None
    topics_count: int
    challenges_count: int
    error_message: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


class JobSummaryResponse(JobStatusResponse):
    retriable: bool


class JobListResponse(BaseModel):
    jobs: list[JobSummaryResponse]
    count: int


class RetryFailedJobsResponse(BaseModel):
    success: bool
    scanned_failed_jobs: int
    retried_count: int
    skipped_active_job: int
    skipped_missing_file: int
    retried_job_ids: list[str]
    message: str


class RecoverStalledJobsResponse(BaseModel):
    success: bool
    scanned_processing_jobs: int
    recovered_count: int
    recovered_job_ids: list[str]
    message: str


class RecoverAndRetryStalledJobsResponse(BaseModel):
    success: bool
    scanned_processing_jobs: int
    recovered_count: int
    retried_count: int
    skipped_active_job: int
    skipped_missing_file: int
    recovered_job_ids: list[str]
    retried_job_ids: list[str]
    message: str


class JobLogsResponse(BaseModel):
    job_id: str
    total_logs: int
    returned_logs: int
    logs: list[str]


class PurgeJobsResponse(BaseModel):
    success: bool
    scanned_terminal_jobs: int
    deleted_count: int
    deleted_job_ids: list[str]
    deleted_source_files: int
    dry_run: bool
    message: str


class JobHealthResponse(BaseModel):
    pending_jobs: int
    processing_jobs: int
    stalled_jobs: int
    completed_jobs_24h: int
    failed_jobs: int
    retriable_failed_jobs: int
    missing_source_failed_jobs: int


class FailureReasonItem(BaseModel):
    reason: str
    count: int
    retriable_count: int


class FailureSummaryResponse(BaseModel):
    total_failed_jobs: int
    returned_reasons: int
    reasons: list[FailureReasonItem]


def _extract_source_filename(job: ImportJob) -> str | None:
    """Best-effort source filename extraction from stored job logs."""
    marker = "Starting processing of "
    try:
        logs = job.get_logs()
    except Exception:
        return None

    for entry in logs:
        if marker in entry:
            return entry.split(marker, 1)[1].strip() or None
    return None


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def _is_job_stale(job: ImportJob, cutoff: datetime) -> bool:
    """Check whether a processing job is older than cutoff, handling naive datetimes."""
    last_updated = job.updated_at or job.created_at
    if not last_updated:
        return False

    if last_updated.tzinfo is None:
        return last_updated < cutoff.replace(tzinfo=None)

    return last_updated < cutoff


def _is_job_newer_or_equal(job: ImportJob, cutoff: datetime) -> bool:
    """Check whether job timestamp is newer than or equal to cutoff."""
    last_updated = job.updated_at or job.created_at
    if not last_updated:
        return False

    if last_updated.tzinfo is None:
        return last_updated >= cutoff.replace(tzinfo=None)

    return last_updated >= cutoff


def _normalize_file_key(file_path: str | None) -> str | None:
    """Normalize a file path into a stable, case-insensitive key for dedupe checks."""
    if not file_path:
        return None

    try:
        return str(Path(file_path).resolve()).lower()
    except Exception:
        try:
            return os.path.abspath(file_path).lower()
        except Exception:
            normalized = str(file_path).strip().lower()
            return normalized or None


def _get_active_file_keys(session: Session) -> set[str]:
    """Collect normalized source file keys for jobs that are already pending/processing."""
    active_jobs = session.exec(
        select(ImportJob).where(ImportJob.status.in_(["pending", "processing"]))
    ).all()

    keys: set[str] = set()
    for active_job in active_jobs:
        file_key = _normalize_file_key(active_job.file_path)
        if file_key:
            keys.add(file_key)

    return keys


def _is_managed_upload_file(file_path: str) -> bool:
    """Return True when a file path points to an existing file within managed upload directory."""
    try:
        source_path = Path(file_path).resolve()
        upload_root = Path(UPLOAD_DIR).resolve()
    except Exception:
        return False

    try:
        if not source_path.is_relative_to(upload_root):
            return False
    except Exception:
        return False

    return source_path.exists() and source_path.is_file()


def _delete_managed_upload_file(file_path: str) -> bool:
    """Delete managed upload source file if present."""
    if not _is_managed_upload_file(file_path):
        return False

    source_path = Path(file_path).resolve()
    try:
        source_path.unlink()
        return True
    except Exception as exc:
        logger.warning("Failed deleting managed upload source file %s: %s", source_path, exc)
        return False


def _normalize_failure_reason(error_message: str | None) -> str:
    """Normalize failure reason text for grouping in diagnostics endpoints."""
    reason = " ".join(str(error_message or "").split()).strip()
    return reason if reason else "unknown"


def _serialize_job_status(job: ImportJob) -> JobStatusResponse:
    """Serialize ImportJob to response payload."""
    return JobStatusResponse(
        id=job.id,
        status=job.status,
        progress_percent=job.progress_percent,
        retriable=(job.status == "error" and bool(job.file_path) and os.path.exists(job.file_path)),
        course_id=job.course_id,
        topics_count=job.topics_count,
        challenges_count=job.challenges_count,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


def _serialize_job_summary(job: ImportJob) -> JobSummaryResponse:
    """Serialize ImportJob with derived retriable flag."""
    status_payload = _serialize_job_status(job)
    return JobSummaryResponse(**status_payload.model_dump())


def _start_import_job_task(job_id: str, file_path: str, source_filename: str | None = None) -> None:
    """Start background import task and log unhandled task exceptions."""
    task = asyncio.create_task(process_file_with_job(job_id, file_path, source_filename=source_filename))

    def _log_task_result(done_task: asyncio.Task) -> None:
        try:
            done_task.result()
        except Exception as exc:
            logger.exception("Import job task failed job_id=%s: %s", job_id, exc)

    task.add_done_callback(_log_task_result)


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
        _start_import_job_task(job_id, file_path, source_filename=filename)
        
        return CreateJobResponse(
            success=True,
            job_id=job_id,
            message="Job created successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=25, ge=1, le=200, description="Maximum jobs to return"),
) -> JobListResponse:
    """List recent import jobs with optional status filtering."""
    try:
        if status and status not in VALID_JOB_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Allowed values: {', '.join(sorted(VALID_JOB_STATUSES))}",
            )

        with Session(engine) as session:
            statement = select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit)
            if status:
                statement = statement.where(ImportJob.status == status)

            jobs = session.exec(statement).all()
            items = [_serialize_job_summary(job) for job in jobs]

        return JobListResponse(jobs=items, count=len(items))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")


@router.post("/jobs/failed/retry")
async def retry_failed_jobs(
    limit: int = Query(default=10, ge=1, le=100, description="Maximum failed jobs to scan"),
) -> RetryFailedJobsResponse:
    """Retry multiple failed jobs that still have accessible source files."""
    try:
        retry_payloads: list[tuple[str, str, str | None]] = []
        retried_job_ids: list[str] = []
        skipped_missing_file = 0
        skipped_active_job = 0

        with Session(engine) as session:
            failed_jobs = session.exec(
                select(ImportJob)
                .where(ImportJob.status == "error")
                .order_by(ImportJob.updated_at.desc())
                .limit(limit)
            ).all()
            reserved_file_keys = _get_active_file_keys(session)

            for failed_job in failed_jobs:
                failed_file_path = failed_job.file_path
                if not failed_file_path or not os.path.exists(failed_file_path):
                    skipped_missing_file += 1
                    continue

                failed_file_key = _normalize_file_key(failed_file_path)
                if not failed_file_key:
                    skipped_missing_file += 1
                    continue

                if failed_file_key in reserved_file_keys:
                    skipped_active_job += 1
                    continue

                retry_job_id = str(uuid.uuid4())
                source_filename = _extract_source_filename(failed_job)
                retry_job = ImportJob(
                    id=retry_job_id,
                    file_path=failed_file_path,
                    status="pending",
                )

                session.add(retry_job)
                retried_job_ids.append(retry_job_id)
                retry_payloads.append((retry_job_id, failed_file_path, source_filename))
                reserved_file_keys.add(failed_file_key)

            session.commit()

        for retry_job_id, retry_file_path, source_filename in retry_payloads:
            _start_import_job_task(retry_job_id, retry_file_path, source_filename=source_filename)

        scanned_failed_jobs = len(failed_jobs)
        return RetryFailedJobsResponse(
            success=True,
            scanned_failed_jobs=scanned_failed_jobs,
            retried_count=len(retried_job_ids),
            skipped_active_job=skipped_active_job,
            skipped_missing_file=skipped_missing_file,
            retried_job_ids=retried_job_ids,
            message=(
                f"Retried {len(retried_job_ids)} failed job(s); "
                f"skipped {skipped_active_job} active-source collision(s); "
                f"skipped {skipped_missing_file} missing source file(s)"
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry failed jobs: {str(e)}")


@router.get("/jobs/health")
async def get_jobs_health() -> JobHealthResponse:
    """Return grinder job health summary for operational dashboards."""
    try:
        stalled_cutoff = _utc_now() - timedelta(minutes=30)
        completed_cutoff = _utc_now() - timedelta(hours=24)

        with Session(engine) as session:
            pending_jobs = session.exec(select(ImportJob).where(ImportJob.status == "pending")).all()
            processing_jobs = session.exec(select(ImportJob).where(ImportJob.status == "processing")).all()
            completed_jobs = session.exec(select(ImportJob).where(ImportJob.status == "completed")).all()
            failed_jobs = session.exec(select(ImportJob).where(ImportJob.status == "error")).all()

        stalled_jobs = sum(1 for job in processing_jobs if _is_job_stale(job, stalled_cutoff))
        completed_jobs_24h = sum(1 for job in completed_jobs if _is_job_newer_or_equal(job, completed_cutoff))
        retriable_failed_jobs = sum(1 for job in failed_jobs if bool(job.file_path) and os.path.exists(job.file_path))
        missing_source_failed_jobs = len(failed_jobs) - retriable_failed_jobs

        return JobHealthResponse(
            pending_jobs=len(pending_jobs),
            processing_jobs=len(processing_jobs),
            stalled_jobs=stalled_jobs,
            completed_jobs_24h=completed_jobs_24h,
            failed_jobs=len(failed_jobs),
            retriable_failed_jobs=retriable_failed_jobs,
            missing_source_failed_jobs=missing_source_failed_jobs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch grinder health: {str(e)}")


@router.get("/jobs/failures/summary")
async def get_failure_summary(
    limit: int = Query(default=20, ge=1, le=200, description="Maximum grouped reasons to return"),
) -> FailureSummaryResponse:
    """Summarize failed jobs by reason and retriable availability."""
    try:
        with Session(engine) as session:
            failed_jobs = session.exec(select(ImportJob).where(ImportJob.status == "error")).all()

        grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "retriable_count": 0})
        for failed_job in failed_jobs:
            reason = _normalize_failure_reason(failed_job.error_message)
            grouped[reason]["count"] += 1
            if failed_job.file_path and os.path.exists(failed_job.file_path):
                grouped[reason]["retriable_count"] += 1

        ordered_reasons = sorted(
            grouped.items(),
            key=lambda item: (item[1]["count"], item[1]["retriable_count"], item[0]),
            reverse=True,
        )[:limit]

        return FailureSummaryResponse(
            total_failed_jobs=len(failed_jobs),
            returned_reasons=len(ordered_reasons),
            reasons=[
                FailureReasonItem(
                    reason=reason,
                    count=stats["count"],
                    retriable_count=stats["retriable_count"],
                )
                for reason, stats in ordered_reasons
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to summarize failures: {str(e)}")


@router.delete("/jobs")
async def purge_jobs(
    statuses: str = Query(default="completed,error", description="Comma-separated terminal statuses to purge"),
    older_than_minutes: int = Query(default=1440, ge=1, le=525600, description="Purge jobs older than this threshold"),
    limit: int = Query(default=200, ge=1, le=1000, description="Maximum terminal jobs to scan"),
    delete_source_files: bool = Query(default=False, description="Delete managed source files for purged jobs"),
    dry_run: bool = Query(default=False, description="Preview purge without deleting anything"),
) -> PurgeJobsResponse:
    """Purge stale terminal jobs (completed/error) to keep the job table tidy."""
    try:
        requested_statuses = [part.strip().lower() for part in statuses.split(",") if part.strip()]
        if not requested_statuses:
            requested_statuses = sorted(TERMINAL_JOB_STATUSES)

        invalid_statuses = sorted(set(requested_statuses) - TERMINAL_JOB_STATUSES)
        if invalid_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid terminal status filter: {', '.join(invalid_statuses)}. "
                    f"Allowed values: {', '.join(sorted(TERMINAL_JOB_STATUSES))}"
                ),
            )

        # Preserve user-specified ordering while deduplicating.
        selected_statuses = list(dict.fromkeys(requested_statuses))
        cutoff = _utc_now() - timedelta(minutes=older_than_minutes)

        with Session(engine) as session:
            terminal_jobs = session.exec(
                select(ImportJob)
                .where(ImportJob.status.in_(selected_statuses))
                .order_by(ImportJob.updated_at.asc())
                .limit(limit)
            ).all()

            eligible_jobs = [job for job in terminal_jobs if _is_job_stale(job, cutoff)]
            deleted_job_ids: list[str] = []
            deleted_source_files = 0

            if not dry_run:
                for job in eligible_jobs:
                    if delete_source_files and job.file_path:
                        if _delete_managed_upload_file(job.file_path):
                            deleted_source_files += 1

                    deleted_job_ids.append(job.id)
                    session.delete(job)

                if deleted_job_ids:
                    session.commit()
            else:
                deleted_job_ids = [job.id for job in eligible_jobs]

        return PurgeJobsResponse(
            success=True,
            scanned_terminal_jobs=len(terminal_jobs),
            deleted_count=len(deleted_job_ids),
            deleted_job_ids=deleted_job_ids,
            deleted_source_files=deleted_source_files,
            dry_run=dry_run,
            message=(
                f"{'Would purge' if dry_run else 'Purged'} {len(deleted_job_ids)} job(s) "
                f"older than {older_than_minutes} minute(s)"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to purge jobs: {str(e)}")


@router.post("/jobs/recover-stalled")
async def recover_stalled_jobs(
    older_than_minutes: int = Query(default=30, ge=1, le=1440, description="Recover processing jobs older than this threshold"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum processing jobs to scan"),
) -> RecoverStalledJobsResponse:
    """Mark stale processing jobs as recoverable errors so they can be retried."""
    try:
        cutoff = _utc_now() - timedelta(minutes=older_than_minutes)
        recovered_job_ids: list[str] = []

        with Session(engine) as session:
            processing_jobs = session.exec(
                select(ImportJob)
                .where(ImportJob.status == "processing")
                .order_by(ImportJob.updated_at.asc())
                .limit(limit)
            ).all()

            for job in processing_jobs:
                if not _is_job_stale(job, cutoff):
                    continue

                job.status = "error"
                job.error_message = (
                    f"Recovered stalled job after >{older_than_minutes} minutes in processing"
                )
                job.add_log(
                    (
                        "Watchdog marked this job as stalled and recoverable. "
                        f"Use retry endpoints to continue processing."
                    ),
                    "warn",
                )
                recovered_job_ids.append(job.id)

            if recovered_job_ids:
                session.commit()

        return RecoverStalledJobsResponse(
            success=True,
            scanned_processing_jobs=len(processing_jobs),
            recovered_count=len(recovered_job_ids),
            recovered_job_ids=recovered_job_ids,
            message=(
                f"Recovered {len(recovered_job_ids)} stalled job(s) "
                f"from {len(processing_jobs)} scanned processing job(s)"
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to recover stalled jobs: {str(e)}")


@router.post("/jobs/recover-stalled/retry")
async def recover_and_retry_stalled_jobs(
    older_than_minutes: int = Query(default=30, ge=1, le=1440, description="Recover processing jobs older than this threshold"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum processing jobs to scan"),
) -> RecoverAndRetryStalledJobsResponse:
    """Recover stalled processing jobs and immediately requeue retry jobs when source files are available."""
    try:
        cutoff = _utc_now() - timedelta(minutes=older_than_minutes)
        retry_payloads: list[tuple[str, str, str | None]] = []
        recovered_job_ids: list[str] = []
        retried_job_ids: list[str] = []
        skipped_missing_file = 0
        skipped_active_job = 0

        with Session(engine) as session:
            processing_jobs = session.exec(
                select(ImportJob)
                .where(ImportJob.status == "processing")
                .order_by(ImportJob.updated_at.asc())
                .limit(limit)
            ).all()

            stale_jobs = [job for job in processing_jobs if _is_job_stale(job, cutoff)]
            stale_ids = {job.id for job in stale_jobs}

            reserved_file_keys: set[str] = set()
            active_jobs = session.exec(
                select(ImportJob).where(ImportJob.status.in_(["pending", "processing"]))
            ).all()
            for active_job in active_jobs:
                if active_job.id in stale_ids:
                    continue
                active_file_key = _normalize_file_key(active_job.file_path)
                if active_file_key:
                    reserved_file_keys.add(active_file_key)

            for stale_job in stale_jobs:
                stale_job.status = "error"
                stale_job.error_message = (
                    f"Recovered stalled job after >{older_than_minutes} minutes in processing"
                )
                stale_job.add_log(
                    (
                        "Watchdog recovered this stalled job and attempted auto-retry. "
                        "Review this job and spawned retries for details."
                    ),
                    "warn",
                )
                recovered_job_ids.append(stale_job.id)

                stale_file_path = stale_job.file_path
                if not stale_file_path or not os.path.exists(stale_file_path):
                    skipped_missing_file += 1
                    stale_job.add_log("Auto-retry skipped: source file missing.", "warn")
                    continue

                stale_file_key = _normalize_file_key(stale_file_path)
                if not stale_file_key:
                    skipped_missing_file += 1
                    stale_job.add_log("Auto-retry skipped: source file path invalid.", "warn")
                    continue

                if stale_file_key in reserved_file_keys:
                    skipped_active_job += 1
                    stale_job.add_log("Auto-retry skipped: active job already exists for this source file.", "warn")
                    continue

                retry_job_id = str(uuid.uuid4())
                source_filename = _extract_source_filename(stale_job)
                retry_job = ImportJob(
                    id=retry_job_id,
                    file_path=stale_file_path,
                    status="pending",
                )
                session.add(retry_job)

                retried_job_ids.append(retry_job_id)
                retry_payloads.append((retry_job_id, stale_file_path, source_filename))
                reserved_file_keys.add(stale_file_key)

            if recovered_job_ids or retried_job_ids:
                session.commit()

        for retry_job_id, retry_file_path, source_filename in retry_payloads:
            _start_import_job_task(retry_job_id, retry_file_path, source_filename=source_filename)

        return RecoverAndRetryStalledJobsResponse(
            success=True,
            scanned_processing_jobs=len(processing_jobs),
            recovered_count=len(recovered_job_ids),
            retried_count=len(retried_job_ids),
            skipped_active_job=skipped_active_job,
            skipped_missing_file=skipped_missing_file,
            recovered_job_ids=recovered_job_ids,
            retried_job_ids=retried_job_ids,
            message=(
                f"Recovered {len(recovered_job_ids)} stalled job(s), retried {len(retried_job_ids)}, "
                f"skipped {skipped_active_job} active-source collision(s), "
                f"skipped {skipped_missing_file} missing/invalid source(s)"
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to recover and retry stalled jobs: {str(e)}")


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get the status of an import job."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            
            return _serialize_job_status(job)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> CreateJobResponse:
    """Retry a failed/cancelled import job using the original uploaded file."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

            if job.status in {"pending", "processing"}:
                raise HTTPException(status_code=409, detail=f"Job {job_id} is still {job.status} and cannot be retried")

            if job.status != "error":
                raise HTTPException(status_code=409, detail=f"Only failed/cancelled jobs can be retried (current status: {job.status})")

            if not job.file_path or not os.path.exists(job.file_path):
                raise HTTPException(
                    status_code=409,
                    detail="Original uploaded file is no longer available. Please upload the file again.",
                )

            original_file_path = job.file_path
            original_file_key = _normalize_file_key(original_file_path)
            if not original_file_key:
                raise HTTPException(
                    status_code=409,
                    detail="Original source file path is invalid. Please upload the file again.",
                )

            active_file_keys = _get_active_file_keys(session)
            if original_file_key in active_file_keys:
                raise HTTPException(
                    status_code=409,
                    detail="An active job already exists for this source file. Wait for it to finish before retrying.",
                )

            source_filename = _extract_source_filename(job)
            retry_job_id = str(uuid.uuid4())
            retry_job_record = ImportJob(
                id=retry_job_id,
                file_path=original_file_path,
                status="pending",
            )
            session.add(retry_job_record)
            session.commit()

        _start_import_job_task(retry_job_id, original_file_path, source_filename=source_filename)

        return CreateJobResponse(
            success=True,
            job_id=retry_job_id,
            message=f"Retry job created from {job_id}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry job: {str(e)}")


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: str,
    tail: int | None = Query(default=None, ge=1, le=2000, description="Return only the most recent N log lines"),
    contains: str | None = Query(default=None, max_length=200, description="Filter log lines by case-insensitive substring"),
    as_text: bool = Query(default=True, description="Return newline-delimited text when true, structured JSON when false"),
) -> str | JobLogsResponse:
    """Get the logs for an import job."""
    try:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

            all_logs = job.get_logs()
            logs = all_logs
            if contains:
                needle = contains.lower()
                logs = [line for line in logs if needle in line.lower()]

            logs = logs[-tail:] if tail else logs

            if as_text:
                return "\n".join(logs)

            return JobLogsResponse(
                job_id=job.id,
                total_logs=len(all_logs),
                returned_logs=len(logs),
                logs=logs,
            )
    
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
            pending_count = len(session.exec(select(ImportJob).where(ImportJob.status == "pending")).all())
            processing_jobs = session.exec(select(ImportJob).where(ImportJob.status == "processing")).all()
            processing_count = len(processing_jobs)
            stalled_cutoff = _utc_now() - timedelta(minutes=30)
            stalled_count = sum(1 for job in processing_jobs if _is_job_stale(job, stalled_cutoff))
            
            return {
                "status": "busy" if processing_count > 0 else "idle",
                "queue_length": pending_count,
                "active_jobs": processing_count,
                "stalled_jobs": stalled_count,
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
