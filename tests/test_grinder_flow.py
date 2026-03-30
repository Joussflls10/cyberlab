"""Core grinder flow tests.

These tests validate:
- Router job creation and status lifecycle
- Service-level file processing with deterministic mocked AI outputs
- Duplicate-file short-circuit behavior with proper count propagation
"""

# pyright: reportMissingImports=false

import os
import sys
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Required at import time by config.Settings
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

import config

config.get_settings.cache_clear()

grinder_router_module = importlib.import_module("routers.grinder")
grinder_service = importlib.import_module("services.grinder")
from models.challenge import Challenge
from models.course import Course, Topic
from models.import_job import ImportJob


class _ImmediateTask:
    """Simple task-like object for immediate coroutine execution in tests."""

    def __init__(self, coro):
        self._result = None
        self._exc = None
        try:
            coro.send(None)
        except StopIteration as stop:
            self._result = stop.value
        except Exception as exc:  # pragma: no cover - surfaced via result()
            self._exc = exc

    def result(self):
        if self._exc:
            raise self._exc
        return self._result

    def add_done_callback(self, callback):
        callback(self)


@pytest.fixture
def test_engine(tmp_path):
    db_path = tmp_path / "grinder_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def patched_grinder(monkeypatch, test_engine, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / "challenge-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(grinder_router_module, "engine", test_engine)
    monkeypatch.setattr(grinder_service, "engine", test_engine)
    monkeypatch.setattr(grinder_router_module, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(grinder_service, "CHALLENGES_CACHE_DIR", cache_dir)

    return {"engine": test_engine, "upload_dir": upload_dir, "cache_dir": cache_dir}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(grinder_router_module.router, prefix="/api/grinder")
    return TestClient(app)


def test_create_job_rejects_invalid_extension(client):
    response = client.post(
        "/api/grinder/jobs",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_create_job_core_flow_updates_status(client, patched_grinder, monkeypatch):
    engine = patched_grinder["engine"]

    async def fake_process_file_with_job(job_id: str, _file_path: str, source_filename: str | None = None) -> None:
        with Session(engine) as session:
            job = session.get(ImportJob, job_id)
            assert job is not None
            job.status = "completed"
            job.progress_percent = 100
            job.topics_count = 2
            job.challenges_count = 5
            job.updated_at = datetime.now(UTC)
            job.completed_at = datetime.now(UTC)
            session.add(job)
            session.commit()

    monkeypatch.setattr(grinder_router_module, "process_file_with_job", fake_process_file_with_job)
    monkeypatch.setattr(grinder_router_module.asyncio, "create_task", lambda coro: _ImmediateTask(coro))

    create_resp = client.post(
        "/api/grinder/jobs",
        files={"file": ("lesson.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )

    assert create_resp.status_code == 200
    payload = create_resp.json()
    assert payload["success"] is True
    assert payload["job_id"]

    status_resp = client.get(f"/api/grinder/jobs/{payload['job_id']}")
    assert status_resp.status_code == 200

    status = status_resp.json()
    assert status["status"] == "completed"
    assert status["progress_percent"] == 100
    assert status["retriable"] is False
    assert status["topics_count"] == 2
    assert status["challenges_count"] == 5


def test_get_job_status_reports_retriable_for_failed_job(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]

    source_file = tmp_path / "failed-status.pdf"
    source_file.write_bytes(b"failed-status")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-status-failed",
                file_path=str(source_file),
                status="error",
                error_message="provider timeout",
            )
        )
        session.commit()

    response = client.get("/api/grinder/jobs/job-status-failed")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "error"
    assert payload["retriable"] is True


def test_list_jobs_filters_and_marks_retriable(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]

    retryable_source = tmp_path / "retryable-source.pdf"
    retryable_source.write_bytes(b"retryable")

    with Session(engine) as session:
        retryable_error = ImportJob(
            id="job-error-retriable",
            file_path=str(retryable_source),
            status="error",
            error_message="transient ai failure",
        )
        retryable_error.add_log("Starting processing of Original-Lab.pdf")

        missing_error = ImportJob(
            id="job-error-missing",
            file_path=str(tmp_path / "missing-source.pdf"),
            status="error",
            error_message="parse failed",
        )

        session.add(retryable_error)
        session.add(missing_error)
        session.add(ImportJob(id="job-processing", file_path=str(tmp_path / "processing.pdf"), status="processing"))
        session.commit()

    response = client.get("/api/grinder/jobs?status=error&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert len(payload["jobs"]) == 2
    assert all(job["status"] == "error" for job in payload["jobs"])

    retriable_map = {job["id"]: job["retriable"] for job in payload["jobs"]}
    assert retriable_map["job-error-retriable"] is True
    assert retriable_map["job-error-missing"] is False


def test_list_jobs_rejects_invalid_status(client):
    response = client.get("/api/grinder/jobs?status=unknown")

    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]


def test_retry_job_requeues_failed_job(client, patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    source_file = tmp_path / "retry-source.pdf"
    source_file.write_bytes(b"retry-source")

    with Session(engine) as session:
        failed_job = ImportJob(
            id="job-failed-retry",
            file_path=str(source_file),
            status="error",
            error_message="Cancelled by user",
        )
        failed_job.add_log("Starting processing of Retry-Lab.pdf")
        session.add(failed_job)
        session.commit()

    task_calls: list[tuple[str, str, str | None]] = []

    async def fake_process_file_with_job(job_id: str, _file_path: str, source_filename: str | None = None) -> None:
        task_calls.append((job_id, _file_path, source_filename))

    monkeypatch.setattr(grinder_router_module, "process_file_with_job", fake_process_file_with_job)
    monkeypatch.setattr(grinder_router_module.asyncio, "create_task", lambda coro: _ImmediateTask(coro))

    response = client.post("/api/grinder/jobs/job-failed-retry/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["job_id"] != "job-failed-retry"

    assert len(task_calls) == 1
    assert task_calls[0][0] == payload["job_id"]
    assert task_calls[0][1] == str(source_file)
    assert task_calls[0][2] == "Retry-Lab.pdf"

    with Session(engine) as session:
        retry_job = session.get(ImportJob, payload["job_id"])
        assert retry_job is not None
        assert retry_job.status == "pending"
        assert retry_job.file_path == str(source_file)


def test_retry_job_rejects_when_source_file_missing(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    missing_file = tmp_path / "source-missing.pdf"

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-missing-source",
                file_path=str(missing_file),
                status="error",
                error_message="AI error",
            )
        )
        session.commit()

    response = client.post("/api/grinder/jobs/job-missing-source/retry")

    assert response.status_code == 409
    assert "no longer available" in response.json()["detail"].lower()


def test_retry_job_rejects_when_active_job_exists_for_same_source(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]

    source_file = tmp_path / "retry-collision.pdf"
    source_file.write_bytes(b"retry-collision")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-retry-collision-failed",
                file_path=str(source_file),
                status="error",
                error_message="temporary failure",
            )
        )
        session.add(
            ImportJob(
                id="job-retry-collision-active",
                file_path=str(source_file),
                status="processing",
            )
        )
        session.commit()

    response = client.post("/api/grinder/jobs/job-retry-collision-failed/retry")
    assert response.status_code == 409
    assert "active job already exists" in response.json()["detail"].lower()


def test_retry_job_rejects_active_job(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    source_file = tmp_path / "active.pdf"
    source_file.write_bytes(b"active")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-active",
                file_path=str(source_file),
                status="processing",
            )
        )
        session.commit()

    response = client.post("/api/grinder/jobs/job-active/retry")

    assert response.status_code == 409
    assert "cannot be retried" in response.json()["detail"].lower()


def test_retry_failed_jobs_bulk_requeues_available_sources_only(client, patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    good_source = tmp_path / "bulk-good.pdf"
    good_source.write_bytes(b"bulk-good")
    missing_source = tmp_path / "bulk-missing.pdf"

    with Session(engine) as session:
        good_failed_job = ImportJob(
            id="bulk-failed-good",
            file_path=str(good_source),
            status="error",
            error_message="temporary provider failure",
        )
        good_failed_job.add_log("Starting processing of Bulk-Good.pdf")

        missing_failed_job = ImportJob(
            id="bulk-failed-missing",
            file_path=str(missing_source),
            status="error",
            error_message="parse failed",
        )

        session.add(good_failed_job)
        session.add(missing_failed_job)
        session.commit()

    task_calls: list[tuple[str, str, str | None]] = []

    async def fake_process_file_with_job(job_id: str, _file_path: str, source_filename: str | None = None) -> None:
        task_calls.append((job_id, _file_path, source_filename))

    monkeypatch.setattr(grinder_router_module, "process_file_with_job", fake_process_file_with_job)
    monkeypatch.setattr(grinder_router_module.asyncio, "create_task", lambda coro: _ImmediateTask(coro))

    response = client.post("/api/grinder/jobs/failed/retry?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_failed_jobs"] == 2
    assert payload["retried_count"] == 1
    assert payload["skipped_active_job"] == 0
    assert payload["skipped_missing_file"] == 1
    assert len(payload["retried_job_ids"]) == 1

    retried_job_id = payload["retried_job_ids"][0]
    assert len(task_calls) == 1
    assert task_calls[0][0] == retried_job_id
    assert task_calls[0][1] == str(good_source)
    assert task_calls[0][2] == "Bulk-Good.pdf"

    with Session(engine) as session:
        retried_job = session.get(ImportJob, retried_job_id)
        assert retried_job is not None
        assert retried_job.status == "pending"
        assert retried_job.file_path == str(good_source)


def test_retry_failed_jobs_bulk_skips_sources_with_active_jobs(client, patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    colliding_source = tmp_path / "bulk-collision.pdf"
    colliding_source.write_bytes(b"collision")
    unique_source = tmp_path / "bulk-unique.pdf"
    unique_source.write_bytes(b"unique")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="bulk-active-collision",
                file_path=str(colliding_source),
                status="processing",
            )
        )
        session.add(
            ImportJob(
                id="bulk-failed-collision",
                file_path=str(colliding_source),
                status="error",
                error_message="timeout",
            )
        )
        session.add(
            ImportJob(
                id="bulk-failed-unique",
                file_path=str(unique_source),
                status="error",
                error_message="timeout",
            )
        )
        session.commit()

    task_calls: list[tuple[str, str, str | None]] = []

    async def fake_process_file_with_job(job_id: str, _file_path: str, source_filename: str | None = None) -> None:
        task_calls.append((job_id, _file_path, source_filename))

    monkeypatch.setattr(grinder_router_module, "process_file_with_job", fake_process_file_with_job)
    monkeypatch.setattr(grinder_router_module.asyncio, "create_task", lambda coro: _ImmediateTask(coro))

    response = client.post("/api/grinder/jobs/failed/retry?limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_failed_jobs"] == 2
    assert payload["retried_count"] == 1
    assert payload["skipped_active_job"] == 1
    assert payload["skipped_missing_file"] == 0
    assert len(payload["retried_job_ids"]) == 1

    assert len(task_calls) == 1
    assert task_calls[0][1] == str(unique_source)


def test_get_job_logs_supports_tail_and_structured_output(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]

    with Session(engine) as session:
        job = ImportJob(id="job-log-tail", file_path=str(tmp_path / "log-tail.pdf"), status="processing")
        job.add_log("first log line")
        job.add_log("second log line")
        job.add_log("third log line")
        session.add(job)
        session.commit()

    text_resp = client.get("/api/grinder/jobs/job-log-tail/logs?tail=2")
    assert text_resp.status_code == 200
    assert "first log line" not in text_resp.text
    assert "second log line" in text_resp.text
    assert "third log line" in text_resp.text

    json_resp = client.get("/api/grinder/jobs/job-log-tail/logs?tail=2&as_text=false")
    assert json_resp.status_code == 200
    payload = json_resp.json()
    assert payload["job_id"] == "job-log-tail"
    assert payload["total_logs"] == 3
    assert payload["returned_logs"] == 2
    assert len(payload["logs"]) == 2
    assert any("second log line" in line for line in payload["logs"])
    assert any("third log line" in line for line in payload["logs"])

    filtered_resp = client.get("/api/grinder/jobs/job-log-tail/logs?contains=second&as_text=false")
    assert filtered_resp.status_code == 200
    filtered_payload = filtered_resp.json()
    assert filtered_payload["total_logs"] == 3
    assert filtered_payload["returned_logs"] == 1
    assert len(filtered_payload["logs"]) == 1
    assert "second log line" in filtered_payload["logs"][0]


def test_recover_stalled_jobs_marks_old_processing_jobs(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    with Session(engine) as session:
        old_job = ImportJob(
            id="job-stalled-old",
            file_path=str(tmp_path / "stalled-old.pdf"),
            status="processing",
            updated_at=now - timedelta(minutes=90),
        )
        recent_job = ImportJob(
            id="job-stalled-recent",
            file_path=str(tmp_path / "stalled-recent.pdf"),
            status="processing",
            updated_at=now - timedelta(minutes=5),
        )
        session.add(old_job)
        session.add(recent_job)
        session.commit()

    response = client.post("/api/grinder/jobs/recover-stalled?older_than_minutes=30&limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_processing_jobs"] == 2
    assert payload["recovered_count"] == 1
    assert payload["recovered_job_ids"] == ["job-stalled-old"]

    with Session(engine) as session:
        old_job = session.get(ImportJob, "job-stalled-old")
        recent_job = session.get(ImportJob, "job-stalled-recent")

        assert old_job is not None
        assert old_job.status == "error"
        assert old_job.error_message is not None
        assert "Recovered stalled job" in old_job.error_message
        assert any("Watchdog marked this job as stalled" in line for line in old_job.get_logs())

        assert recent_job is not None
        assert recent_job.status == "processing"


def test_recover_and_retry_stalled_jobs_requeues_recoverable_sources(client, patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    stale_source = tmp_path / "stale-retry.pdf"
    stale_source.write_bytes(b"stale-retry")

    with Session(engine) as session:
        stalled_job = ImportJob(
            id="job-stalled-retry",
            file_path=str(stale_source),
            status="processing",
        )
        stalled_job.add_log("Starting processing of Stale-Retry.pdf")
        stalled_job.updated_at = now - timedelta(minutes=90)
        session.add(stalled_job)
        session.commit()

    task_calls: list[tuple[str, str, str | None]] = []

    async def fake_process_file_with_job(job_id: str, _file_path: str, source_filename: str | None = None) -> None:
        task_calls.append((job_id, _file_path, source_filename))

    monkeypatch.setattr(grinder_router_module, "process_file_with_job", fake_process_file_with_job)
    monkeypatch.setattr(grinder_router_module.asyncio, "create_task", lambda coro: _ImmediateTask(coro))

    response = client.post("/api/grinder/jobs/recover-stalled/retry?older_than_minutes=30&limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_processing_jobs"] == 1
    assert payload["recovered_count"] == 1
    assert payload["retried_count"] == 1
    assert payload["skipped_active_job"] == 0
    assert payload["skipped_missing_file"] == 0
    assert payload["recovered_job_ids"] == ["job-stalled-retry"]
    assert len(payload["retried_job_ids"]) == 1

    assert len(task_calls) == 1
    assert task_calls[0][1] == str(stale_source)
    assert task_calls[0][2] == "Stale-Retry.pdf"

    retried_job_id = payload["retried_job_ids"][0]
    with Session(engine) as session:
        recovered = session.get(ImportJob, "job-stalled-retry")
        retried = session.get(ImportJob, retried_job_id)

        assert recovered is not None
        assert recovered.status == "error"
        assert recovered.error_message is not None
        assert "Recovered stalled job" in recovered.error_message

        assert retried is not None
        assert retried.status == "pending"
        assert retried.file_path == str(stale_source)


def test_recover_and_retry_stalled_jobs_skips_missing_and_active_collisions(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    collision_source = tmp_path / "collision-stale.pdf"
    collision_source.write_bytes(b"collision")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-stalled-missing",
                file_path=str(tmp_path / "missing-stale.pdf"),
                status="processing",
                updated_at=now - timedelta(minutes=80),
            )
        )
        session.add(
            ImportJob(
                id="job-stalled-collision",
                file_path=str(collision_source),
                status="processing",
                updated_at=now - timedelta(minutes=75),
            )
        )
        session.add(
            ImportJob(
                id="job-active-collision",
                file_path=str(collision_source),
                status="processing",
                updated_at=now - timedelta(minutes=5),
            )
        )
        session.commit()

    response = client.post("/api/grinder/jobs/recover-stalled/retry?older_than_minutes=30&limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_processing_jobs"] == 3
    assert payload["recovered_count"] == 2
    assert payload["retried_count"] == 0
    assert payload["skipped_active_job"] == 1
    assert payload["skipped_missing_file"] == 1
    assert set(payload["recovered_job_ids"]) == {"job-stalled-missing", "job-stalled-collision"}


def test_grinder_status_reports_stalled_jobs(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="job-status-stalled",
                file_path=str(tmp_path / "status-stalled.pdf"),
                status="processing",
                updated_at=now - timedelta(minutes=45),
            )
        )
        session.add(
            ImportJob(
                id="job-status-pending",
                file_path=str(tmp_path / "status-pending.pdf"),
                status="pending",
            )
        )
        session.commit()

    response = client.get("/api/grinder/status")
    assert response.status_code == 200

    payload = response.json()
    assert payload["active_jobs"] == 1
    assert payload["queue_length"] == 1
    assert payload["stalled_jobs"] == 1


def test_purge_jobs_deletes_old_terminal_jobs_and_managed_files(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    upload_dir = patched_grinder["upload_dir"]
    now = datetime.now(UTC)

    managed_error_file = upload_dir / "old-error.pdf"
    managed_error_file.write_bytes(b"old-error")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="purge-old-completed",
                file_path=str(tmp_path / "completed.pdf"),
                status="completed",
                updated_at=now - timedelta(minutes=180),
                completed_at=now - timedelta(minutes=179),
            )
        )
        session.add(
            ImportJob(
                id="purge-old-error",
                file_path=str(managed_error_file),
                status="error",
                error_message="test error",
                updated_at=now - timedelta(minutes=170),
            )
        )
        session.add(
            ImportJob(
                id="purge-recent-error",
                file_path=str(upload_dir / "recent.pdf"),
                status="error",
                error_message="recent error",
                updated_at=now - timedelta(minutes=10),
            )
        )
        session.commit()

    response = client.delete("/api/grinder/jobs?older_than_minutes=60&limit=10&delete_source_files=true")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned_terminal_jobs"] == 3
    assert payload["deleted_count"] == 2
    assert set(payload["deleted_job_ids"]) == {"purge-old-completed", "purge-old-error"}
    assert payload["deleted_source_files"] == 1

    assert not managed_error_file.exists()

    with Session(engine) as session:
        assert session.get(ImportJob, "purge-old-completed") is None
        assert session.get(ImportJob, "purge-old-error") is None
        assert session.get(ImportJob, "purge-recent-error") is not None


def test_purge_jobs_dry_run_keeps_records(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="purge-dry-run",
                file_path=str(tmp_path / "dry-run.pdf"),
                status="completed",
                updated_at=now - timedelta(minutes=120),
            )
        )
        session.commit()

    response = client.delete("/api/grinder/jobs?older_than_minutes=30&dry_run=true")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["dry_run"] is True
    assert payload["deleted_count"] == 1
    assert payload["deleted_job_ids"] == ["purge-dry-run"]

    with Session(engine) as session:
        assert session.get(ImportJob, "purge-dry-run") is not None


def test_purge_jobs_rejects_non_terminal_status_filter(client):
    response = client.delete("/api/grinder/jobs?statuses=processing")

    assert response.status_code == 400
    assert "Invalid terminal status filter" in response.json()["detail"]


def test_jobs_health_summarizes_queue_and_failure_recoverability(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]
    now = datetime.now(UTC)

    retriable_error_file = tmp_path / "health-retriable.pdf"
    retriable_error_file.write_bytes(b"retriable")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="health-pending",
                file_path=str(tmp_path / "pending.pdf"),
                status="pending",
                updated_at=now - timedelta(minutes=2),
            )
        )
        session.add(
            ImportJob(
                id="health-processing-recent",
                file_path=str(tmp_path / "processing-recent.pdf"),
                status="processing",
                updated_at=now - timedelta(minutes=5),
            )
        )
        session.add(
            ImportJob(
                id="health-processing-stalled",
                file_path=str(tmp_path / "processing-stalled.pdf"),
                status="processing",
                updated_at=now - timedelta(minutes=80),
            )
        )
        session.add(
            ImportJob(
                id="health-completed-recent",
                file_path=str(tmp_path / "completed-recent.pdf"),
                status="completed",
                updated_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1),
            )
        )
        session.add(
            ImportJob(
                id="health-completed-old",
                file_path=str(tmp_path / "completed-old.pdf"),
                status="completed",
                updated_at=now - timedelta(days=2),
                completed_at=now - timedelta(days=2),
            )
        )
        session.add(
            ImportJob(
                id="health-error-retriable",
                file_path=str(retriable_error_file),
                status="error",
                error_message="provider timeout",
                updated_at=now - timedelta(minutes=30),
            )
        )
        session.add(
            ImportJob(
                id="health-error-missing",
                file_path=str(tmp_path / "missing-error.pdf"),
                status="error",
                error_message="parse failure",
                updated_at=now - timedelta(minutes=40),
            )
        )
        session.commit()

    response = client.get("/api/grinder/jobs/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["pending_jobs"] == 1
    assert payload["processing_jobs"] == 2
    assert payload["stalled_jobs"] == 1
    assert payload["completed_jobs_24h"] == 1
    assert payload["failed_jobs"] == 2
    assert payload["retriable_failed_jobs"] == 1
    assert payload["missing_source_failed_jobs"] == 1


def test_failure_summary_groups_reasons_and_counts_retriable(client, patched_grinder, tmp_path):
    engine = patched_grinder["engine"]

    retriable_source = tmp_path / "failure-retriable.pdf"
    retriable_source.write_bytes(b"retry")

    with Session(engine) as session:
        session.add(
            ImportJob(
                id="failure-1",
                file_path=str(retriable_source),
                status="error",
                error_message="provider timeout",
            )
        )
        session.add(
            ImportJob(
                id="failure-2",
                file_path=str(tmp_path / "missing-1.pdf"),
                status="error",
                error_message="provider timeout",
            )
        )
        session.add(
            ImportJob(
                id="failure-3",
                file_path=str(tmp_path / "missing-2.pdf"),
                status="error",
                error_message="parse failed",
            )
        )
        session.commit()

    response = client.get("/api/grinder/jobs/failures/summary?limit=10")
    assert response.status_code == 200

    payload = response.json()
    assert payload["total_failed_jobs"] == 3
    assert payload["returned_reasons"] == 2
    assert len(payload["reasons"]) == 2

    top_reason = payload["reasons"][0]
    assert top_reason["reason"] == "provider timeout"
    assert top_reason["count"] == 2
    assert top_reason["retriable_count"] == 1

    secondary = payload["reasons"][1]
    assert secondary["reason"] == "parse failed"
    assert secondary["count"] == 1
    assert secondary["retriable_count"] == 0


@pytest.mark.asyncio
async def test_process_file_with_job_creates_course_topics_and_challenges(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"fake-pdf-data")

    job_id = "job-core-flow"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(
        grinder_service,
        "parse_pdf",
        lambda _path: "Linux basics\n\nNetworking fundamentals\n\nService hardening",
    )

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Linux Ops",
            "topics": [
                {"name": "Linux Basics", "order": 1},
                {"name": "Networking", "order": 2},
            ],
        }

    async def fake_generate_challenges(topic_data):
        topic_name = topic_data["name"]
        slug = topic_name.lower().replace(" ", "_")
        return [
            {
                "question": f"Run `uname -a` and save the output to `{slug}_system_info.txt` for topic {topic_name}.",
                "hint": None,
                "type": "command",
                "sandbox_image": "rocky9-base",
                "difficulty": "easy",
                "validation_script": f"#!/bin/bash\n[ -s {slug}_system_info.txt ] || exit 1\ngrep -q Linux {slug}_system_info.txt || exit 1\nexit 0",
                "expected_output": None,
            }
        ]

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    await grinder_service.process_file_with_job(job_id, str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.progress_percent == 100
        assert job.topics_count == 2
        assert job.challenges_count == 2
        assert job.course_id is not None

        course = session.get(Course, job.course_id)
        assert course is not None
        assert course.title == "Linux Ops"
        assert course.topic_count == 2
        assert course.challenge_count == 2

        topics = session.exec(select(Topic).where(Topic.course_id == course.id)).all()
        challenges = session.exec(select(Challenge).where(Challenge.course_id == course.id)).all()

        assert len(topics) == 2
        assert len(challenges) == 2


@pytest.mark.asyncio
async def test_process_file_with_job_cleans_managed_upload_source_on_success(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    managed_upload_dir = tmp_path / "managed-drop"
    managed_upload_dir.mkdir(parents=True, exist_ok=True)
    source_file = managed_upload_dir / "cleanup-success.pdf"
    source_file.write_bytes(b"cleanup-success-data")

    monkeypatch.setattr(grinder_service, "GRINDER_UPLOAD_DIR", managed_upload_dir.resolve())

    job_id = "job-cleanup-success"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "Topic text")

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Cleanup Course",
            "topics": [{"name": "Git Basics", "order": 1}],
            "_generation_mode": "ai",
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Initialize a Git repository in the current directory.",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\n[ -d .git ] && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                }
            ],
            "skipped_topics": [],
            "_generation_mode": "ai",
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    await grinder_service.process_file_with_job(job_id, str(source_file), source_filename="cleanup-success.pdf")

    assert not source_file.exists()


@pytest.mark.asyncio
async def test_process_file_with_job_keeps_managed_source_on_error_for_retry(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    managed_upload_dir = tmp_path / "managed-drop"
    managed_upload_dir.mkdir(parents=True, exist_ok=True)
    source_file = managed_upload_dir / "cleanup-error.pdf"
    source_file.write_bytes(b"cleanup-error-data")

    monkeypatch.setattr(grinder_service, "GRINDER_UPLOAD_DIR", managed_upload_dir.resolve())

    job_id = "job-cleanup-error"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(
        grinder_service,
        "parse_pdf",
        lambda _path: (_ for _ in ()).throw(ValueError("parse exploded")),
    )

    with pytest.raises(ValueError, match="parse exploded"):
        await grinder_service.process_file_with_job(job_id, str(source_file), source_filename="cleanup-error.pdf")

    assert source_file.exists()

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "error"


@pytest.mark.asyncio
async def test_process_file_with_job_duplicate_short_circuit_sets_counts(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    source_file = tmp_path / "duplicate.pdf"
    source_file.write_bytes(b"duplicate-content")
    source_hash = grinder_service.compute_source_hash(str(source_file))

    existing_course_id = "existing-course"
    with Session(engine) as session:
        session.add(
            Course(
                id=existing_course_id,
                title="Already Imported",
                description="existing",
                source_file=source_file.name,
                source_hash=source_hash,
                topic_count=3,
                challenge_count=9,
            )
        )
        session.add(ImportJob(id="job-dup", file_path=str(source_file), status="pending"))
        session.commit()

    # Ensure parse step is never reached for duplicate short-circuit
    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: (_ for _ in ()).throw(AssertionError("parse_pdf should not run")))

    await grinder_service.process_file_with_job("job-dup", str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, "job-dup")
        assert job is not None
        assert job.status == "completed"
        assert job.course_id == existing_course_id
        assert job.topics_count == 3
        assert job.challenges_count == 9
        assert job.progress_percent == 100


@pytest.mark.asyncio
async def test_process_file_with_job_logs_skipped_non_sandboxable_items(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    source_file = tmp_path / "skip-log.pdf"
    source_file.write_bytes(b"skip-log-data")

    job_id = "job-skip-logging"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "Topic text")

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Skip-Aware Course",
            "topics": [{"name": "Ansible Remote SSH", "order": 1}],
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Run ansible localhost -m ping",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\ncommand -v ansible >/dev/null 2>&1 && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                }
            ],
            "skipped_topics": [
                {
                    "name": "SSH from control node to managed node",
                    "reason": "multi-host: requires two networked machines",
                }
            ],
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    await grinder_service.process_file_with_job(job_id, str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "completed"

        logs = job.get_logs()
        assert any("Skipped 1 multi-host/external challenges" in line for line in logs)


def test_cache_save_load_handles_topic_names_with_slashes(monkeypatch, tmp_path):
    cache_root = tmp_path / "challenge-cache"
    monkeypatch.setattr(grinder_service, "CHALLENGES_CACHE_DIR", cache_root)

    course_id = "course-cache-test"
    topic_name = "Virtual appliances en OVF/OVA standaard"
    challenges_payload = [{"question": "demo", "type": "command"}]

    grinder_service.save_challenge_cache(course_id, topic_name, challenges_payload)
    loaded = grinder_service.load_challenge_cache(course_id, topic_name)

    assert loaded == challenges_payload

    course_dir = cache_root / course_id
    assert course_dir.exists()

    json_files = list(course_dir.glob("**/*.json"))
    assert len(json_files) == 1
    assert json_files[0].parent == course_dir


@pytest.mark.asyncio
async def test_extract_topics_uses_multiple_chunks_and_merges(monkeypatch):
    monkeypatch.setattr(grinder_service, "MAX_CHUNK_TOKENS", 1)

    class FakeChunkClient:
        async def call_model(self, model_key, system, user, max_tokens=2000):
            assert model_key == "grinder"
            if "SECTION_ONE" in user:
                return json.dumps(
                    {
                        "course_name": "IaC Course",
                        "topics": [
                            {
                                "name": "Git Setup",
                                "order": 1,
                                "key_concepts": ["repository init"],
                                "tools_mentioned": ["git"],
                                "commands_mentioned": ["git init"],
                                "procedures": ["Initialize repository"],
                            }
                        ],
                    }
                )
            if "SECTION_TWO" in user:
                return json.dumps(
                    {
                        "course_name": "IaC Course",
                        "topics": [
                            {
                                "name": "Git Setup",
                                "order": 1,
                                "key_concepts": ["commit workflow"],
                                "tools_mentioned": ["git"],
                                "commands_mentioned": ["git status"],
                                "procedures": ["Check status"],
                            },
                            {
                                "name": "Ansible Install",
                                "order": 2,
                                "key_concepts": ["control node"],
                                "tools_mentioned": ["ansible"],
                                "commands_mentioned": ["ansible --version"],
                                "procedures": ["Install ansible"],
                            },
                        ],
                    }
                )
            return json.dumps({"course_name": "IaC Course", "topics": []})

    monkeypatch.setattr(grinder_service, "get_client", lambda: FakeChunkClient())

    text = "SECTION_ONE\n\nSECTION_TWO\n\nSECTION_THREE"
    topics_data = await grinder_service.extract_topics(text)

    assert topics_data["_generation_mode"] == "ai"
    assert topics_data["_chunk_count"] >= 2
    assert len(topics_data["topics"]) == 2

    git_topic = next(t for t in topics_data["topics"] if t["name"] == "Git Setup")
    assert "git init" in git_topic["commands_mentioned"]
    assert "git status" in git_topic["commands_mentioned"]


@pytest.mark.asyncio
async def test_process_file_preserves_original_source_filename(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    source_file = tmp_path / "generated-uuid-file.pdf"
    source_file.write_bytes(b"fake-pdf-data")

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "SECTION_ONE\n\nSECTION_TWO")

    async def fake_enrich_content(text: str):
        return {"text": text, "_generation_mode": "fallback", "_fallback_reason": "test"}

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Filename Test Course",
            "topics": [{"name": "Git Setup", "order": 1}],
            "_generation_mode": "ai",
            "_chunk_count": 1,
            "_chunks_with_topics": 1,
            "_chunk_failures": 0,
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Initialize a Git repository in the current directory.",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\n[ -d .git ] && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                }
            ],
            "skipped_topics": [],
            "_generation_mode": "ai",
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "enrich_content", fake_enrich_content)
    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    result = await grinder_service.process_file(str(source_file), source_filename="Labo-2.pdf")

    with Session(engine) as session:
        course = session.get(Course, result["course_id"])
        assert course is not None
        assert course.source_file == "Labo-2.pdf"


def test_local_sanity_rejects_generic_filler_templates():
    rejected = grinder_service._local_sanity_review_challenge(
        "Verify `echo` is installed by checking its version or help output.",
        "#!/bin/bash\ncommand -v echo >/dev/null 2>&1 && exit 0 || exit 1",
        "Linux Basics",
    )

    assert rejected["approved"] is False
    assert "generic" in (rejected.get("reason") or "").lower()


def test_ansible_low_value_filter_rejects_version_only():
    reason = grinder_service._is_low_value_ansible_challenge(
        "Run ansible --version and save output to ansible_version.txt",
        "#!/bin/bash\nansible --version > ansible_version.txt\nexit 0",
        {"name": "Ansible Installation on Ubuntu", "commands_mentioned": ["ansible"]},
    )

    assert reason is not None
    assert "low-value" in reason.lower() or "version/help-only" in reason.lower()


def test_ansible_low_value_filter_accepts_playbook_task():
    reason = grinder_service._is_low_value_ansible_challenge(
        "Write /root/bootstrap.yml and validate it with ansible-playbook --syntax-check",
        "#!/bin/bash\nansible-playbook --syntax-check /root/bootstrap.yml -i localhost, > /dev/null 2>&1 || exit 1\nexit 0",
        {"name": "Ansible Bootstrap Playbook", "commands_mentioned": ["ansible-playbook"]},
    )

    assert reason is None


def test_weak_validation_script_detector_flags_unconditional_pipeline_pass():
    reason = grinder_service._is_weak_validation_script(
        "#!/bin/bash\n"
        "[ -f checklist.md ] || exit 1\n"
        "grep -Ec '^- \\[ \\]' checklist.md | awk '{exit ($1>=3)?0:1}'\n"
        "exit 0"
    )

    assert reason is not None
    assert "pipeline failure" in reason.lower() or "always passes" in reason.lower()


def test_weak_validation_script_detector_flags_invalid_shebang():
    reason = grinder_service._is_weak_validation_script(
        "#!/binbash\n"
        "[ -f /tmp/demo.txt ] || exit 1\n"
        "exit 0"
    )

    assert reason is not None
    assert "shebang" in reason.lower()


def test_fallback_ansible_topic_generates_playbook_and_config_checks():
    challenges = grinder_service._fallback_generate_challenges(
        {
            "name": "Ansible Bootstrap Playbook",
            "commands_mentioned": ["ansible-playbook", "ansible-config"],
            "tools_mentioned": ["ansible"],
        }
    )

    assert len(challenges) >= 3
    questions = "\n".join(str(c.get("question") or "") for c in challenges).lower()
    scripts = "\n".join(str(c.get("validation_script") or "") for c in challenges).lower()

    assert "playbook" in questions
    assert "ansible.cfg" in questions or "inventory" in questions
    assert "--syntax-check" in scripts


@pytest.mark.asyncio
async def test_process_file_with_job_skips_topic_when_below_minimum_threshold(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]

    source_file = tmp_path / "below-minimum.pdf"
    source_file.write_bytes(b"below-minimum-data")

    job_id = "job-below-minimum"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "Topic text")

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Minimum Gate Course",
            "topics": [{"name": "Git Basics", "order": 1}],
            "_generation_mode": "ai",
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Initialize a Git repository in the current directory.",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\n[ -d .git ] && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                },
                {
                    "question": "Set a local Git username for this repository.",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\ngit config --local user.name >/dev/null 2>&1 && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                },
            ],
            "skipped_topics": [],
            "_generation_mode": "ai",
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    with pytest.raises(ValueError, match="No publishable topics remained"):
        await grinder_service.process_file_with_job(job_id, str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "error"
        assert job.topics_count == 0
        assert job.challenges_count == 0

        logs = job.get_logs()
        assert any("quality gate" in line.lower() for line in logs)


@pytest.mark.asyncio
async def test_process_file_with_job_dedupes_templates_across_topics(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    source_file = tmp_path / "cross-topic-dedupe.pdf"
    source_file.write_bytes(b"cross-topic-data")

    job_id = "job-cross-topic-dedupe"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "Topic text")

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Dedup Course",
            "topics": [
                {"name": "Git Basics", "order": 1},
                {"name": "Git Workflow", "order": 2},
            ],
            "_generation_mode": "ai",
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Initialize a Git repository in the current directory.",
                    "hint": None,
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\n[ -d .git ] && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                }
            ],
            "skipped_topics": [],
            "_generation_mode": "ai",
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    await grinder_service.process_file_with_job(job_id, str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.challenges_count == 1

        logs = job.get_logs()
        assert any("duplicate template across topics" in line.lower() for line in logs)


@pytest.mark.asyncio
async def test_process_file_with_job_rejects_vm_snapshot_challenge(patched_grinder, monkeypatch, tmp_path):
    engine = patched_grinder["engine"]
    monkeypatch.setattr(grinder_service, "MIN_APPROVED_CHALLENGES_PER_TOPIC", 1)

    source_file = tmp_path / "vm-snapshot.pdf"
    source_file.write_bytes(b"vm-snapshot-data")

    job_id = "job-sanity-reject"
    with Session(engine) as session:
        session.add(ImportJob(id=job_id, file_path=str(source_file), status="pending"))
        session.commit()

    monkeypatch.setattr(grinder_service, "parse_pdf", lambda _path: "VM Snapshot procedures")

    async def fake_extract_topics(_text: str):
        return {
            "course_name": "Hypervisor Ops",
            "topics": [{"name": "Lab Environment Preparation & VM Snapshots", "order": 1}],
            "_generation_mode": "ai",
        }

    async def fake_generate_challenges(_topic_data):
        return {
            "challenges": [
                {
                    "question": "Run `snapshot creation` in the terminal to verify your environment for topic 'Lab Environment Preparation & VM Snapshots'.",
                    "hint": "Use the terminal and verify the command exits successfully.",
                    "type": "command",
                    "sandbox_type": "single",
                    "sandbox_image": "rocky9-base",
                    "difficulty": "easy",
                    "validation_script": "#!/bin/bash\ncommand -v snapshot >/dev/null 2>&1 && exit 0 || exit 1",
                    "expected_output": None,
                    "skipped_reason": None,
                }
            ],
            "skipped_topics": [],
            "_generation_mode": "ai",
        }

    async def fake_review_validation_script(_q, script, _image):
        return {"valid": True, "issues": None, "fixed_script": script}

    monkeypatch.setattr(grinder_service, "extract_topics", fake_extract_topics)
    monkeypatch.setattr(grinder_service, "generate_challenges", fake_generate_challenges)
    monkeypatch.setattr(grinder_service, "review_validation_script", fake_review_validation_script)

    with pytest.raises(ValueError, match="No publishable topics remained"):
        await grinder_service.process_file_with_job(job_id, str(source_file))

    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        assert job is not None
        assert job.status == "error"
        assert job.challenges_count == 0

        assert job.course_id is None

        logs = job.get_logs()
        assert any("Rejected:" in line and "snapshot creation" in line for line in logs)
