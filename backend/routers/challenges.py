"""Challenges Router - Handles challenge lifecycle."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from services.sandbox import start_sandbox, run_validation, stop_sandbox
from models.challenge import Challenge, get_active_challenges, get_challenge_by_id
from models.progress import UserProgress, create_or_update_progress
from database import get_session

router = APIRouter()


class StartResponse(BaseModel):
    container_id: str
    port: int


class SubmitRequest(BaseModel):
    user_id: str


class SubmitResponse(BaseModel):
    passed: bool
    output: str


class SkipRequest(BaseModel):
    user_id: str


@router.post("/{challenge_id}/start", response_model=StartResponse)
async def start_challenge(challenge_id: str):
    """Start a challenge sandbox. Returns container_id and port."""
    session = next(get_session())
    try:
        challenge = get_challenge_by_id(session, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        # Start sandbox - SYNCHRONOUS, do NOT await
        result = start_sandbox(challenge_id, challenge.sandbox_image)
        
        return StartResponse(
            container_id=result["container_id"],
            port=result["port"],
        )
    finally:
        session.close()


@router.post("/{challenge_id}/submit", response_model=SubmitResponse)
async def submit_challenge(challenge_id: str, request: SubmitRequest):
    """Submit a challenge solution. Runs validation and updates progress."""
    session = next(get_session())
    try:
        challenge = get_challenge_by_id(session, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        # Get user's active container from progress
        progress = session.query(UserProgress).filter(
            UserProgress.user_id == request.user_id,
            UserProgress.challenge_id == challenge_id,
        ).first()
        
        if not progress or not progress.container_id:
            raise HTTPException(status_code=400, detail="No active sandbox found. Start the challenge first.")
        
        # Run validation - SYNCHRONOUS, do NOT await
        result = run_validation(progress.container_id, challenge.validation_script)
        
        # Update progress
        passed = result["success"]
        create_or_update_progress(
            session=session,
            id=str(uuid.uuid4()) if not progress else progress.id,
            user_id=request.user_id,
            course_id=challenge.course_id,
            challenge_id=challenge_id,
            status="passed" if passed else "attempted",
            attempts=(progress.attempts + 1) if progress else 1,
            passed_at=datetime.utcnow() if passed else None,
            last_attempted_at=datetime.utcnow(),
        )
        
        # Stop sandbox
        stop_sandbox(progress.container_id)
        
        return SubmitResponse(
            passed=passed,
            output=result["output"],
        )
    finally:
        session.close()


@router.post("/{challenge_id}/skip")
async def skip_challenge(challenge_id: str, request: SkipRequest):
    """Mark a challenge as skipped."""
    session = next(get_session())
    try:
        challenge = get_challenge_by_id(session, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        create_or_update_progress(
            session=session,
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            course_id=challenge.course_id,
            challenge_id=challenge_id,
            status="skipped",
            last_attempted_at=datetime.utcnow(),
        )
        
        return {"status": "skipped", "challenge_id": challenge_id}
    finally:
        session.close()


@router.get("/")
async def list_challenges(topic_id: Optional[str] = None, status: Optional[str] = None):
    """List challenges, optionally filtered by topic or status."""
    session = next(get_session())
    try:
        challenges = get_active_challenges(session)
        
        if topic_id:
            challenges = [c for c in challenges if c.topic_id == topic_id]
        
        # Convert to dicts for JSON serialization
        result = []
        for c in challenges:
            result.append({
                "id": c.id,
                "course_id": c.course_id,
                "topic_id": c.topic_id,
                "type": c.type,
                "question": c.question,
                "hint": c.hint,
                "difficulty": c.difficulty,
                "order": c.order,
            })
        
        return result
    finally:
        session.close()


@router.get("/{challenge_id}")
async def get_challenge(challenge_id: str):
    """Get a single challenge by ID."""
    session = next(get_session())
    try:
        challenge = get_challenge_by_id(session, challenge_id)
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        return {
            "id": challenge.id,
            "course_id": challenge.course_id,
            "topic_id": challenge.topic_id,
            "type": challenge.type,
            "question": challenge.question,
            "hint": challenge.hint,
            "sandbox_image": challenge.sandbox_image,
            "difficulty": challenge.difficulty,
            "order": challenge.order,
        }
    finally:
        session.close()
