"""Course and Topic models for CyberLab."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime


class Course(SQLModel, table=True):
    """Course table - represents a learning course."""

    __tablename__ = "courses"

    id: str = Field(primary_key=True)
    title: str = Field(index=True, max_length=200)
    description: str = Field(max_length=2000)
    source_file: str = Field(max_length=500)
    source_hash: str = Field(max_length=64, index=True)  # SHA256 for duplicate detection
    topic_count: int = Field(default=0)
    challenge_count: int = Field(default=0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    topics: List["Topic"] = Relationship(back_populates="course", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    challenges: List["Challenge"] = Relationship(back_populates="course")
    progress_records: List["UserProgress"] = Relationship(back_populates="course")

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, title='{self.title}')>"


class Topic(SQLModel, table=True):
    """Topic table - represents a topic within a course."""

    __tablename__ = "topics"

    id: str = Field(primary_key=True)
    course_id: str = Field(foreign_key="courses.id", index=True, ondelete="CASCADE")
    name: str = Field(max_length=200)
    order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    course: Optional[Course] = Relationship(back_populates="topics")

    def __repr__(self) -> str:
        return f"<Topic(id={self.id}, name='{self.name}', course_id={self.course_id})>"


# Helper functions
def get_active_courses(session) -> List[Course]:
    """Get all active courses."""
    return session.query(Course).filter(Course.is_active == True).all()


def get_course_by_id(session, course_id: str) -> Optional[Course]:
    """Get a course by its ID."""
    return session.get(Course, course_id)


def get_topics_for_course(session, course_id: str) -> List[Topic]:
    """Get all topics for a course, ordered by position."""
    return (
        session.query(Topic)
        .filter(Topic.course_id == course_id)
        .order_by(Topic.order)
        .all()
    )


def create_course(
    session,
    id: str,
    title: str,
    description: str,
    source_file: str,
    source_hash: str,
    **kwargs
) -> Course:
    """Create a new course."""
    course = Course(
        id=id,
        title=title,
        description=description,
        source_file=source_file,
        source_hash=source_hash,
        **kwargs
    )
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


def create_topic(
    session,
    id: str,
    course_id: str,
    name: str,
    order: int = 0,
    **kwargs
) -> Topic:
    """Create a new topic for a course."""
    topic = Topic(
        id=id,
        course_id=course_id,
        name=name,
        order=order,
        **kwargs
    )
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic
