"""UserProgress model for tracking user learning progress."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import UTC, datetime


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class UserProgress(SQLModel, table=True):
    """UserProgress table - tracks user progress through courses and challenges."""

    __tablename__ = "user_progress"

    id: str = Field(primary_key=True)
    user_id: str = Field(max_length=100, index=True)  # External user identifier
    course_id: str = Field(foreign_key="courses.id", index=True, ondelete="CASCADE")
    challenge_id: Optional[str] = Field(default=None, foreign_key="challenges.id", index=True, ondelete="SET NULL")
    topic_id: Optional[str] = Field(default=None, foreign_key="topics.id", index=True, ondelete="SET NULL")
    
    # Progress tracking
    status: str = Field(default="unseen", max_length=20, index=True)  # unseen/attempted/passed/skipped
    attempts: int = Field(default=0)
    passed_at: Optional[datetime] = Field(default=None, index=True)
    last_attempted_at: Optional[datetime] = Field(default=None)

    # Relationships
    course: Optional["Course"] = Relationship(back_populates="progress_records")
    challenge: Optional["Challenge"] = Relationship(back_populates="progress_records")

    def __repr__(self) -> str:
        return f"<UserProgress(id={self.id}, user_id='{self.user_id}', status={self.status})>"


# Helper functions
def get_user_progress(session, user_id: str, course_id: str) -> Optional[UserProgress]:
    """Get user's progress for a specific course."""
    return (
        session.query(UserProgress)
        .filter(
            UserProgress.user_id == user_id,
            UserProgress.course_id == course_id,
            UserProgress.challenge_id == None
        )
        .first()
    )


def get_user_challenge_progress(
    session, user_id: str, challenge_id: str
) -> Optional[UserProgress]:
    """Get user's progress for a specific challenge."""
    return (
        session.query(UserProgress)
        .filter(
            UserProgress.user_id == user_id,
            UserProgress.challenge_id == challenge_id
        )
        .first()
    )


def get_all_user_progress(session, user_id: str) -> List[UserProgress]:
    """Get all progress records for a user."""
    return session.query(UserProgress).filter(UserProgress.user_id == user_id).all()


def get_completed_courses(session, user_id: str) -> List[UserProgress]:
    """Get all completed courses for a user."""
    return (
        session.query(UserProgress)
        .filter(
            UserProgress.user_id == user_id,
            UserProgress.status == "passed",
            UserProgress.challenge_id == None
        )
        .all()
    )


def create_or_update_progress(
    session,
    id: str,
    user_id: str,
    course_id: str,
    challenge_id: Optional[str] = None,
    **kwargs
) -> UserProgress:
    """Create or update user progress record."""
    if challenge_id:
        progress = get_user_challenge_progress(session, user_id, challenge_id)
    else:
        progress = get_user_progress(session, user_id, course_id)

    if progress:
        for key, value in kwargs.items():
            if hasattr(progress, key):
                setattr(progress, key, value)
        progress.last_attempted_at = _utc_now()
    else:
        progress = UserProgress(
            id=id,
            user_id=user_id,
            course_id=course_id,
            challenge_id=challenge_id,
            **kwargs
        )
        session.add(progress)

    session.commit()
    session.refresh(progress)
    return progress


def mark_challenge_completed(
    session, id: str, user_id: str, challenge_id: str
) -> UserProgress:
    """Mark a challenge as completed for a user."""
    from .challenge import Challenge
    
    challenge = session.get(Challenge, challenge_id)
    if not challenge:
        raise ValueError(f"Challenge {challenge_id} not found")

    progress = create_or_update_progress(
        session,
        id=id,
        user_id=user_id,
        course_id=challenge.course_id,
        challenge_id=challenge_id,
        status="passed",
        attempts=1,
        passed_at=_utc_now(),
    )
    return progress


def get_user_stats(session, user_id: str) -> dict:
    """Get statistics for a user."""
    all_progress = get_all_user_progress(session, user_id)
    completed = [p for p in all_progress if p.status == "passed" and p.challenge_id is None]
    challenge_completed = [p for p in all_progress if p.status == "passed" and p.challenge_id is not None]
    
    return {
        "courses_completed": len(completed),
        "challenges_completed": len(challenge_completed),
        "total_attempts": sum(p.attempts for p in all_progress),
    }
