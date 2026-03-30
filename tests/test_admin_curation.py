"""Admin curation endpoint tests (lean coverage).

Covers runtime quality metrics and selected bulk activation/deactivation.
"""

# pyright: reportMissingImports=false

import os
import sys
import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")

admin_router_module = importlib.import_module("routers.admin")
from models.course import Course, Topic
from models.challenge import Challenge
from models.progress import UserProgress


@pytest.fixture
def test_engine(tmp_path):
    db_path = tmp_path / "admin_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(monkeypatch, test_engine):
    def fake_get_session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(admin_router_module, "get_session", fake_get_session)

    app = FastAPI()
    app.include_router(admin_router_module.router, prefix="/api/admin")
    return TestClient(app)


def _seed_course_with_challenges(engine):
    with Session(engine) as session:
        session.add(
            Course(
                id="course-1",
                title="Admin Curation Course",
                description="desc",
                source_file="seed.pdf",
                source_hash="hash-1",
                topic_count=1,
                challenge_count=2,
            )
        )
        session.add(Topic(id="topic-1", course_id="course-1", name="Git Basics", order=1))

        session.add(
            Challenge(
                id="challenge-low",
                course_id="course-1",
                topic_id="topic-1",
                type="command",
                question="Run git --version and save output to git_version.txt",
                sandbox_image="rocky9-base",
                validation_script="#!/bin/bash\nexit 0",
                difficulty="easy",
                is_active=True,
                order=1,
            )
        )
        session.add(
            Challenge(
                id="challenge-high",
                course_id="course-1",
                topic_id="topic-1",
                type="command",
                question="Initialize /root/git-lab, commit README.md with message 'Initial commit', then create branch feature/hardening.",
                sandbox_image="rocky9-base",
                validation_script=(
                    "#!/bin/bash\n"
                    "test -d /root/git-lab/.git || exit 1\n"
                    "git -C /root/git-lab log --oneline | grep -q 'Initial commit' || exit 1\n"
                    "git -C /root/git-lab branch --show-current | grep -q 'feature/hardening' || exit 1\n"
                    "exit 0"
                ),
                difficulty="medium",
                is_active=True,
                order=2,
            )
        )

        session.add(
            UserProgress(
                id="progress-1",
                user_id="u1",
                course_id="course-1",
                challenge_id="challenge-high",
                status="passed",
                attempts=2,
            )
        )
        session.add(
            UserProgress(
                id="progress-2",
                user_id="u2",
                course_id="course-1",
                challenge_id="challenge-high",
                status="attempted",
                attempts=3,
            )
        )

        session.commit()


def test_admin_list_includes_quality_metrics(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.get("/api/admin/courses/course-1/challenges?include_inactive=true")
    assert response.status_code == 200

    payload = response.json()
    challenges = payload["challenges"]
    assert len(challenges) == 2

    low = next(c for c in challenges if c["id"] == "challenge-low")
    high = next(c for c in challenges if c["id"] == "challenge-high")

    assert "quality_score" in low
    assert "quality_flags" in low
    assert "weak_validation_reason" in low
    assert "low_value_prompt" in low["quality_flags"]
    assert "weak_validation" in low["quality_flags"]

    assert high["attempts"] == 5
    assert high["passes"] == 1
    assert high["pass_rate"] == 0.2
    assert high["quality_score"] > low["quality_score"]


def test_admin_bulk_set_active_updates_selected_only(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post(
        "/api/admin/courses/course-1/challenges/bulk-set-active",
        json={
            "challenge_ids": ["challenge-low", "challenge-high", "challenge-missing"],
            "is_active": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 3
    assert payload["found"] == 2
    assert payload["updated"] == 2
    assert payload["is_active"] is False
    assert payload["missing_ids"] == ["challenge-missing"]

    with Session(test_engine) as session:
        low = session.get(Challenge, "challenge-low")
        high = session.get(Challenge, "challenge-high")
        assert low is not None and low.is_active is False
        assert high is not None and high.is_active is False


def test_admin_bulk_set_active_rejects_empty_selection(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post(
        "/api/admin/courses/course-1/challenges/bulk-set-active",
        json={"challenge_ids": [], "is_active": True},
    )

    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]


def test_admin_auto_curate_deactivates_low_quality_challenges(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post("/api/admin/courses/course-1/challenges/auto-curate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["scanned"] == 2
    assert payload["deactivated"] == 1

    affected_ids = [challenge["id"] for challenge in payload["affected_challenges"]]
    assert "challenge-low" in affected_ids
    assert "challenge-high" not in affected_ids

    with Session(test_engine) as session:
        low = session.get(Challenge, "challenge-low")
        high = session.get(Challenge, "challenge-high")
        assert low is not None and low.is_active is False
        assert high is not None and high.is_active is True


def test_admin_quality_metrics_flag_invalid_shebang(client, test_engine):
    _seed_course_with_challenges(test_engine)

    with Session(test_engine) as session:
        session.add(
            Challenge(
                id="challenge-bad-shebang",
                course_id="course-1",
                topic_id="topic-1",
                type="command",
                question="Create /root/demo.txt and verify it exists.",
                sandbox_image="rocky9-base",
                validation_script="#!/binbash\n[ -f /root/demo.txt ] || exit 1\nexit 0",
                difficulty="easy",
                is_active=True,
                order=3,
            )
        )
        session.commit()

    response = client.get("/api/admin/courses/course-1/challenges?include_inactive=true")
    assert response.status_code == 200

    payload = response.json()
    challenge = next(item for item in payload["challenges"] if item["id"] == "challenge-bad-shebang")
    assert "weak_validation" in challenge["quality_flags"]
    assert challenge["weak_validation_reason"] == "invalid or unsupported shebang"


def test_admin_auto_curate_dry_run_does_not_mutate(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post(
        "/api/admin/courses/course-1/challenges/auto-curate",
        json={"dry_run": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["deactivated"] == 0
    assert payload["would_deactivate"] == 1

    with Session(test_engine) as session:
        low = session.get(Challenge, "challenge-low")
        high = session.get(Challenge, "challenge-high")
        assert low is not None and low.is_active is True
        assert high is not None and high.is_active is True


def test_admin_auto_curate_respects_max_deactivations(client, test_engine):
    _seed_course_with_challenges(test_engine)

    with Session(test_engine) as session:
        session.add(
            Challenge(
                id="challenge-low-2",
                course_id="course-1",
                topic_id="topic-1",
                type="command",
                question="Verify your environment for Git Basics.",
                sandbox_image="rocky9-base",
                validation_script="#!/bin/bash\ncommand -v git >/dev/null 2>&1 && exit 0 || exit 1",
                difficulty="easy",
                is_active=True,
                order=4,
            )
        )
        session.commit()

    response = client.post(
        "/api/admin/courses/course-1/challenges/auto-curate",
        json={"max_deactivations": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["max_deactivations"] == 1
    assert payload["total_candidates_before_cap"] == 2
    assert payload["candidates_after_cap"] == 1
    assert payload["cap_applied"] is True
    assert payload["candidates"] == 1
    assert payload["deactivated"] == 1

    with Session(test_engine) as session:
        low_1 = session.get(Challenge, "challenge-low")
        low_2 = session.get(Challenge, "challenge-low-2")
        inactive_count = int(bool(low_1 and not low_1.is_active)) + int(bool(low_2 and not low_2.is_active))
        assert inactive_count == 1


def test_admin_auto_curate_rejects_negative_max_deactivations(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post(
        "/api/admin/courses/course-1/challenges/auto-curate",
        json={"max_deactivations": -1},
    )

    assert response.status_code == 422


def test_admin_auto_curate_rejects_out_of_range_min_quality_score(client, test_engine):
    _seed_course_with_challenges(test_engine)

    response = client.post(
        "/api/admin/courses/course-1/challenges/auto-curate",
        json={"min_quality_score": 101},
    )

    assert response.status_code == 422
