"""Admin Router - Challenge curation endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select
from typing import Dict, List, Optional
import re

from database import get_session
from models.challenge import Challenge
from models.course import Topic, get_course_by_id
from models.progress import UserProgress

router = APIRouter()


class BulkSetActivePayload(BaseModel):
    challenge_ids: List[str]
    is_active: bool


class AutoCuratePayload(BaseModel):
    min_quality_score: float = Field(default=60.0, ge=0.0, le=100.0)
    deactivate_flagged: bool = True
    deactivate_below_threshold: bool = True
    include_inactive: bool = False
    dry_run: bool = False
    max_deactivations: Optional[int] = Field(default=None, ge=0)


def _is_low_value_prompt(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return True

    if "verify your environment" in q:
        return True

    version_or_help = any(token in q for token in ["--version", " --help", "-help"])
    if version_or_help and any(token in q for token in ["save output", "capture output", "_version.txt", "_help.txt"]):
        return True

    if any(token in q for token in ["write notes", "notes.md", "checklist", "explain concept"]):
        return True

    return False


def _weak_validation_reason(validation_script: str) -> Optional[str]:
    script = (validation_script or "").strip()
    if not script:
        return "missing validation script"

    first_line = script.splitlines()[0].strip() if script.splitlines() else ""
    if first_line.startswith("#!"):
        if not re.fullmatch(r"^#!\s*(/bin/(ba)?sh|/usr/bin/env\s+bash)\s*$", first_line):
            return "invalid or unsupported shebang"

    if re.fullmatch(r"(?is)\s*(#!/bin/(ba)?sh\s*)?exit\s+0\s*;?\s*", script):
        return "validation script always passes"

    lower = script.lower()
    if "command -v" in lower and not any(
        token in lower
        for token in [
            "grep -q",
            "test -f",
            "test -d",
            "stat -c",
            "ansible-playbook",
            "git -c",
            "git log",
            "git branch",
            "python3 -c",
        ]
    ):
        return "validation checks command presence only"

    lines = [ln.strip().lower() for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if lines and lines[-1] == "exit 0":
        for line in lines[:-1]:
            if "|" in line and "|| exit 1" not in line and "&&" not in line and not line.startswith("if "):
                return "pipeline result may be ignored before unconditional success"

    return None


def _compute_quality_metrics(challenge: Challenge, attempts: int, passes: int) -> Dict[str, object]:
    flags: List[str] = []

    if _is_low_value_prompt(challenge.question):
        flags.append("low_value_prompt")

    weak_reason = _weak_validation_reason(challenge.validation_script)
    if weak_reason:
        flags.append("weak_validation")

    score = 100.0
    if "low_value_prompt" in flags:
        score -= 35
    if "weak_validation" in flags:
        score -= 45

    if len((challenge.question or "").strip()) < 60:
        score -= 5

    script_lower = (challenge.validation_script or "").lower()
    if any(token in script_lower for token in ["grep -q", "stat -c", "ansible-playbook", "git log", "python3 -c", "ss -", "ip route"]):
        score += 5

    attempts = max(attempts, passes)
    pass_rate: Optional[float] = None
    if attempts > 0:
        pass_rate = passes / attempts
        if pass_rate < 0.15:
            score -= 5
        elif pass_rate > 0.95:
            score -= 5

    score = max(0.0, min(100.0, score))

    return {
        "quality_score": round(score, 1),
        "quality_flags": flags,
        "weak_validation_reason": weak_reason,
        "attempts": attempts,
        "passes": passes,
        "pass_rate": round(pass_rate, 3) if pass_rate is not None else None,
    }


def _progress_aggregate_for_course(session, course_id: str) -> Dict[str, Dict[str, int]]:
    progress_records = session.exec(
        select(UserProgress).where(UserProgress.course_id == course_id).where(UserProgress.challenge_id != None)  # noqa: E711
    ).all()

    progress_by_challenge: Dict[str, Dict[str, int]] = {}
    for record in progress_records:
        challenge_id = record.challenge_id
        if not challenge_id:
            continue
        aggregate = progress_by_challenge.setdefault(challenge_id, {"attempts": 0, "passes": 0})
        aggregate["attempts"] += max(int(record.attempts or 0), 0)
        if record.status == "passed" or record.passed_at is not None:
            aggregate["passes"] += 1

    return progress_by_challenge


@router.get("/courses/{course_id}/challenges")
async def list_course_challenges_for_curation(course_id: str, include_inactive: bool = True):
    """List generated challenges for a course with topic metadata for admin curation."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        topics = session.exec(select(Topic).where(Topic.course_id == course_id)).all()
        topic_map = {t.id: t for t in topics}

        challenge_query = select(Challenge).where(Challenge.course_id == course_id)
        if not include_inactive:
            challenge_query = challenge_query.where(Challenge.is_active == True)  # noqa: E712
        challenges = session.exec(challenge_query).all()

        progress_by_challenge = _progress_aggregate_for_course(session, course_id)

        def sort_key(ch: Challenge):
            topic = topic_map.get(ch.topic_id)
            topic_order = topic.order if topic else 0
            return (topic_order, ch.order, ch.created_at)

        challenges_sorted = sorted(challenges, key=sort_key)

        return {
            "course": {
                "id": course.id,
                "title": course.title,
                "description": course.description,
            },
            "challenges": [
                {
                    **{
                        "id": c.id,
                        "topic_id": c.topic_id,
                        "topic_name": topic_map.get(c.topic_id).name if topic_map.get(c.topic_id) else "Unknown Topic",
                        "type": c.type,
                        "difficulty": c.difficulty,
                        "question": c.question,
                        "sandbox_image": c.sandbox_image,
                        "validation_script": c.validation_script,
                        "is_active": c.is_active,
                        "order": c.order,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    },
                    **_compute_quality_metrics(
                        c,
                        progress_by_challenge.get(c.id, {}).get("attempts", 0),
                        progress_by_challenge.get(c.id, {}).get("passes", 0),
                    ),
                }
                for c in challenges_sorted
            ],
        }
    finally:
        session.close()


@router.post("/courses/{course_id}/challenges/auto-curate")
async def auto_curate_course_challenges(course_id: str, payload: Optional[AutoCuratePayload] = None):
    """Automatically hide low-quality challenges for a course based on runtime metrics."""
    session = next(get_session())
    try:
        payload = payload or AutoCuratePayload()

        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        challenge_query = select(Challenge).where(Challenge.course_id == course_id)
        if not payload.include_inactive:
            challenge_query = challenge_query.where(Challenge.is_active == True)  # noqa: E712

        challenges = session.exec(challenge_query).all()
        progress_by_challenge = _progress_aggregate_for_course(session, course_id)

        candidates: List[Dict[str, object]] = []
        ranked_candidates: List[Dict[str, object]] = []

        for challenge in challenges:
            metrics = _compute_quality_metrics(
                challenge,
                progress_by_challenge.get(challenge.id, {}).get("attempts", 0),
                progress_by_challenge.get(challenge.id, {}).get("passes", 0),
            )

            quality_flags = metrics.get("quality_flags", [])
            quality_score = float(metrics.get("quality_score", 100.0))

            reasons: List[str] = []
            if payload.deactivate_flagged and quality_flags:
                reasons.append("quality_flags")
            if payload.deactivate_below_threshold and quality_score < payload.min_quality_score:
                reasons.append("below_threshold")

            if not reasons:
                continue

            ranked_candidates.append(
                {
                    "challenge": challenge,
                    "metrics": metrics,
                    "reasons": reasons,
                }
            )

        ranked_candidates.sort(
            key=lambda item: (
                float(item["metrics"].get("quality_score", 100.0)),
                str(item["challenge"].id),
            )
        )

        total_candidates_before_cap = len(ranked_candidates)

        if payload.max_deactivations is not None:
            ranked_candidates = ranked_candidates[: payload.max_deactivations]

        candidates_after_cap = len(ranked_candidates)
        cap_applied = candidates_after_cap < total_candidates_before_cap

        deactivated = 0
        affected_challenges: List[Dict[str, object]] = []
        for item in ranked_candidates:
            challenge = item["challenge"]
            metrics = item["metrics"]
            reasons = item["reasons"]

            candidates.append(item)
            affected_challenges.append(
                {
                    "id": challenge.id,
                    "quality_score": metrics.get("quality_score"),
                    "quality_flags": metrics.get("quality_flags", []),
                    "weak_validation_reason": metrics.get("weak_validation_reason"),
                    "reasons": reasons,
                }
            )

        would_deactivate = sum(1 for item in candidates if bool(item["challenge"].is_active))

        if not payload.dry_run:
            for item in candidates:
                challenge = item["challenge"]
                if challenge.is_active:
                    challenge.is_active = False
                    session.add(challenge)
                    deactivated += 1
            session.commit()
        else:
            session.rollback()

        return {
            "success": True,
            "course_id": course_id,
            "scanned": len(challenges),
            "candidates": len(candidates),
            "total_candidates_before_cap": total_candidates_before_cap,
            "candidates_after_cap": candidates_after_cap,
            "cap_applied": cap_applied,
            "deactivated": deactivated,
            "would_deactivate": would_deactivate,
            "min_quality_score": payload.min_quality_score,
            "dry_run": payload.dry_run,
            "max_deactivations": payload.max_deactivations,
            "affected_challenges": affected_challenges,
            "active_only_scan": not payload.include_inactive,
        }
    finally:
        session.close()


@router.post("/challenges/{challenge_id}/approve")
async def approve_challenge(challenge_id: str):
    """Mark a challenge as approved/active."""
    session = next(get_session())
    try:
        challenge = session.get(Challenge, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        challenge.is_active = True
        session.add(challenge)
        session.commit()

        return {"success": True, "challenge_id": challenge_id, "is_active": True}
    finally:
        session.close()


@router.delete("/challenges/{challenge_id}")
async def deactivate_challenge(challenge_id: str):
    """Soft-delete a challenge by deactivating it from learner visibility."""
    session = next(get_session())
    try:
        challenge = session.get(Challenge, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        challenge.is_active = False
        session.add(challenge)
        session.commit()

        return {"success": True, "challenge_id": challenge_id, "is_active": False}
    finally:
        session.close()


@router.post("/courses/{course_id}/challenges/hide-all")
async def hide_all_course_challenges(course_id: str):
    """Soft-hide all active challenges for a course."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        challenges = session.exec(select(Challenge).where(Challenge.course_id == course_id)).all()
        updated = 0
        for challenge in challenges:
            if challenge.is_active:
                challenge.is_active = False
                session.add(challenge)
                updated += 1

        session.commit()
        return {
            "success": True,
            "course_id": course_id,
            "updated": updated,
            "is_active": False,
        }
    finally:
        session.close()


@router.post("/courses/{course_id}/challenges/approve-all")
async def approve_all_course_challenges(course_id: str):
    """Bulk-approve (activate) all hidden challenges for a course."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        challenges = session.exec(select(Challenge).where(Challenge.course_id == course_id)).all()
        updated = 0
        for challenge in challenges:
            if not challenge.is_active:
                challenge.is_active = True
                session.add(challenge)
                updated += 1

        session.commit()
        return {
            "success": True,
            "course_id": course_id,
            "updated": updated,
            "is_active": True,
        }
    finally:
        session.close()


@router.post("/courses/{course_id}/challenges/bulk-set-active")
async def bulk_set_course_challenges_active(course_id: str, payload: BulkSetActivePayload):
    """Bulk activate/deactivate selected challenge IDs for a course."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        challenge_ids = [str(challenge_id).strip() for challenge_id in payload.challenge_ids if str(challenge_id).strip()]
        if not challenge_ids:
            raise HTTPException(status_code=400, detail="challenge_ids cannot be empty")

        challenges = session.exec(
            select(Challenge)
            .where(Challenge.course_id == course_id)
            .where(Challenge.id.in_(challenge_ids))
        ).all()

        found_ids = {challenge.id for challenge in challenges}
        missing_ids = [challenge_id for challenge_id in challenge_ids if challenge_id not in found_ids]

        updated = 0
        for challenge in challenges:
            if challenge.is_active != payload.is_active:
                challenge.is_active = payload.is_active
                session.add(challenge)
                updated += 1

        session.commit()
        return {
            "success": True,
            "course_id": course_id,
            "requested": len(challenge_ids),
            "found": len(found_ids),
            "updated": updated,
            "is_active": payload.is_active,
            "missing_ids": missing_ids,
        }
    finally:
        session.close()
