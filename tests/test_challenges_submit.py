"""Challenge submit behavior tests.

Ensures failed submissions keep sandbox alive for retries,
while successful submissions still trigger sandbox cleanup.
"""

# pyright: reportMissingImports=false

import os
import sys
import importlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

challenges_router_module = importlib.import_module("routers.challenges")


class _DummySession:
    class _DummyQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

    def query(self, *_args, **_kwargs):
        return self._DummyQuery()

    def close(self):
        return None


class _DummyChallenge:
    id = "challenge-1"
    course_id = "course-1"
    topic_id = "topic-1"
    validation_script = "#!/bin/bash\nexit 1"


def _build_client(monkeypatch, *, validation_success: bool, stopped_ids: list[str]):
    def fake_get_session():
        yield _DummySession()

    def fake_get_challenge_by_id(_session, _challenge_id):
        return _DummyChallenge()

    def fake_run_validation(_container_id, _validation_script):
        return {"success": validation_success, "output": "ok" if validation_success else "fail"}

    def fake_stop_sandbox(container_id):
        stopped_ids.append(container_id)
        return {"container_id": container_id, "status": "stopped"}

    def fake_create_or_update_progress(**_kwargs):
        return None

    monkeypatch.setattr(challenges_router_module, "get_session", fake_get_session)
    monkeypatch.setattr(challenges_router_module, "get_challenge_by_id", fake_get_challenge_by_id)
    monkeypatch.setattr(challenges_router_module, "run_validation", fake_run_validation)
    monkeypatch.setattr(challenges_router_module, "stop_sandbox", fake_stop_sandbox)
    monkeypatch.setattr(challenges_router_module, "create_or_update_progress", fake_create_or_update_progress)

    app = FastAPI()
    app.include_router(challenges_router_module.router, prefix="/api/challenges")
    return TestClient(app)


def test_submit_failure_keeps_sandbox_running(monkeypatch):
    stopped_ids: list[str] = []
    client = _build_client(monkeypatch, validation_success=False, stopped_ids=stopped_ids)

    response = client.post(
        "/api/challenges/challenge-1/submit",
        json={"container_id": "cid-fail", "user_id": "default"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is False
    assert stopped_ids == []


def test_submit_success_stops_sandbox(monkeypatch):
    stopped_ids: list[str] = []
    client = _build_client(monkeypatch, validation_success=True, stopped_ids=stopped_ids)

    response = client.post(
        "/api/challenges/challenge-1/submit",
        json={"container_id": "cid-pass", "user_id": "default"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert stopped_ids == ["cid-pass"]
