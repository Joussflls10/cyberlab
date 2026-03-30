"""Courses Router - Handles course CRUD operations."""

from fastapi import APIRouter, HTTPException
from sqlmodel import select, delete

from models.course import Course, Topic, get_active_courses, get_course_by_id, get_topics_for_course
from models.challenge import Challenge
from models.progress import UserProgress
from models.import_job import ImportJob
from database import get_session

router = APIRouter()


@router.get("/")
async def list_courses():
    """List all courses with progress summary."""
    session = next(get_session())
    try:
        courses = get_active_courses(session)
        
        # Convert to dicts for JSON serialization
        result = []
        for course in courses:
            result.append({
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "topic_count": course.topic_count,
                "challenge_count": course.challenge_count,
                "created_at": course.created_at.isoformat() if course.created_at else None,
            })
        
        return result
    finally:
        session.close()


@router.get("/{course_id}")
async def get_course(course_id: str):
    """Get a course with its topics."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        topics = get_topics_for_course(session, course_id)
        
        return {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "source_file": course.source_file,
            "topic_count": course.topic_count,
            "challenge_count": course.challenge_count,
            "created_at": course.created_at.isoformat() if course.created_at else None,
            "topics": [
                {
                    "id": t.id,
                    "name": t.name,
                    "order": t.order,
                }
                for t in topics
            ],
        }
    finally:
        session.close()


@router.get("/{course_id}/topics")
async def get_course_topics(course_id: str):
    """Get topics for a course with challenge counts."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        topics = get_topics_for_course(session, course_id)
        
        # Get challenge counts per topic
        result = []
        for topic in topics:
            challenge_count = session.query(Challenge).filter(
                Challenge.topic_id == topic.id
            ).count()
            
            result.append({
                "id": topic.id,
                "name": topic.name,
                "order": topic.order,
                "challenge_count": challenge_count,
            })
        
        return result
    finally:
        session.close()


@router.delete("/{course_id}")
async def delete_course(course_id: str):
    """Delete a course and all related data (cascade)."""
    session = next(get_session())
    try:
        course = get_course_by_id(session, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        # Explicitly delete dependents to avoid ORM trying to NULL non-nullable FKs.
        session.exec(delete(UserProgress).where(UserProgress.course_id == course_id))
        session.exec(delete(Challenge).where(Challenge.course_id == course_id))
        session.exec(delete(Topic).where(Topic.course_id == course_id))
        session.exec(delete(ImportJob).where(ImportJob.course_id == course_id))

        session.delete(course)
        session.commit()

        return {"success": True, "message": "Course deleted", "course_id": course_id}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete course: {str(e)}")
    finally:
        session.close()
