"""Progress Router - Handles user progress tracking and analytics."""

from fastapi import APIRouter, HTTPException
from typing import List

from models.progress import (
    UserProgress,
    get_user_stats,
    get_all_user_progress,
    get_completed_courses,
)
from models.course import Course
from models.challenge import Challenge
from database import get_session

router = APIRouter()


@router.get("/summary")
async def get_progress_summary(user_id: str = "default"):
    """Get overall progress stats for a user."""
    session = next(get_session())
    try:
        stats = get_user_stats(session, user_id)
        return stats
    finally:
        session.close()


@router.get("/course/{course_id}")
async def get_course_progress(course_id: str, user_id: str = "default"):
    """Get per-course progress breakdown."""
    session = next(get_session())
    try:
        # Get course
        course = session.get(Course, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        # Get all challenges for course
        challenges = session.query(Challenge).filter(
            Challenge.course_id == course_id
        ).all()
        
        # Get user's progress for these challenges
        challenge_ids = [c.id for c in challenges]
        progress_records = session.query(UserProgress).filter(
            UserProgress.user_id == user_id,
            UserProgress.challenge_id.in_(challenge_ids),
        ).all()
        
        # Build progress map
        progress_map = {p.challenge_id: p for p in progress_records}
        
        # Calculate stats
        total = len(challenges)
        passed = sum(1 for c in challenges if progress_map.get(c.id, {}).status == "passed")
        attempted = sum(1 for c in challenges if progress_map.get(c.id, {}).status == "attempted")
        skipped = sum(1 for c in challenges if progress_map.get(c.id, {}).status == "skipped")
        
        return {
            "course_id": course_id,
            "course_title": course.title,
            "total_challenges": total,
            "passed": passed,
            "attempted": attempted,
            "skipped": skipped,
            "unseen": total - passed - attempted - skipped,
            "completion_pct": round(passed / total * 100, 1) if total > 0 else 0,
        }
    finally:
        session.close()


@router.get("/weak-topics")
async def get_weak_topics(user_id: str = "default", threshold: float = 0.6):
    """Get topics with pass rate below threshold."""
    session = next(get_session())
    try:
        # Get all user's progress
        progress = get_all_user_progress(session, user_id)
        
        # Group by topic
        from collections import defaultdict
        topic_stats = defaultdict(lambda: {"total": 0, "passed": 0})
        
        for p in progress:
            if p.challenge_id and p.topic_id:
                topic_stats[p.topic_id]["total"] += 1
                if p.status == "passed":
                    topic_stats[p.topic_id]["passed"] += 1
        
        # Find weak topics
        weak_topics = []
        for topic_id, stats in topic_stats.items():
            if stats["total"] > 0:
                pass_rate = stats["passed"] / stats["total"]
                if pass_rate < threshold:
                    topic = session.get(Course, topic_id)
                    weak_topics.append({
                        "topic_id": topic_id,
                        "topic_name": topic.name if topic else "Unknown",
                        "pass_rate": round(pass_rate, 2),
                        "total": stats["total"],
                        "passed": stats["passed"],
                    })
        
        # Sort by pass rate (worst first)
        weak_topics.sort(key=lambda x: x["pass_rate"])
        
        return weak_topics
    finally:
        session.close()
