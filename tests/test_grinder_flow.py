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
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine


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

    monkeypatch.setattr(grinder_router_module, "engine", test_engine)
    monkeypatch.setattr(grinder_service, "engine", test_engine)
    monkeypatch.setattr(grinder_router_module, "UPLOAD_DIR", str(upload_dir))

    return {"engine": test_engine, "upload_dir": upload_dir}


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
            job.updated_at = datetime.utcnow()
            job.completed_at = datetime.utcnow()
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
    assert status["topics_count"] == 2
    assert status["challenges_count"] == 5


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

        topics = session.query(Topic).filter(Topic.course_id == course.id).all()
        challenges = session.query(Challenge).filter(Challenge.course_id == course.id).all()

        assert len(topics) == 2
        assert len(challenges) == 2


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
