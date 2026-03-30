"""Challenge model for CyberLab."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import UTC, datetime


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class Challenge(SQLModel, table=True):
    """Challenge table - represents a hands-on challenge/exercise."""

    __tablename__ = "challenges"

    id: str = Field(primary_key=True)
    course_id: str = Field(foreign_key="courses.id", index=True, ondelete="CASCADE")
    topic_id: str = Field(foreign_key="topics.id")
    type: str = Field(max_length=50)
    question: str = Field(max_length=5000)
    hint: Optional[str] = Field(default=None, max_length=1000)
    sandbox_image: str = Field(max_length=200)
    validation_script: str = Field(max_length=10000)
    expected_output: Optional[str] = Field(default=None, max_length=5000)
    order: int = Field(default=0, index=True)
    difficulty: str = Field(default="easy", max_length=20)  # easy, medium, hard
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)

    # Relationships
    course: Optional["Course"] = Relationship(back_populates="challenges")
    progress_records: List["UserProgress"] = Relationship(back_populates="challenge")

    def __repr__(self) -> str:
        return f"<Challenge(id={self.id}, question='{self.question[:50]}...', type={self.type})>"


# Helper functions
def get_active_challenges(session, course_id: Optional[str] = None) -> List[Challenge]:
    """Get all active challenges, optionally filtered by course."""
    query = session.query(Challenge).filter(Challenge.is_active == True)
    if course_id:
        query = query.filter(Challenge.course_id == course_id)
    return query.all()


def get_challenge_by_id(session, challenge_id: str) -> Optional[Challenge]:
    """Get a challenge by its ID."""
    return session.get(Challenge, challenge_id)


def get_challenges_for_course(session, course_id: str) -> List[Challenge]:
    """Get all challenges for a course."""
    return (
        session.query(Challenge)
        .filter(Challenge.course_id == course_id)
        .filter(Challenge.is_active == True)
        .all()
    )


def create_challenge(
    session,
    id: str,
    course_id: str,
    topic_id: str,
    type: str,
    question: str,
    sandbox_image: str,
    validation_script: str,
    **kwargs
) -> Challenge:
    """Create a new challenge."""
    challenge = Challenge(
        id=id,
        course_id=course_id,
        topic_id=topic_id,
        type=type,
        question=question,
        sandbox_image=sandbox_image,
        validation_script=validation_script,
        **kwargs
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    return challenge


def update_challenge_attempt(session, challenge_id: str, user_id: str, success: bool) -> None:
    """Update challenge attempt count for a user."""
    from .progress import UserProgress
    progress = (
        session.query(UserProgress)
        .filter(
            UserProgress.user_id == user_id,
            UserProgress.challenge_id == challenge_id
        )
        .first()
    )
    if progress:
        progress.attempts += 1
        if success:
            progress.passed_at = _utc_now()
        session.commit()
