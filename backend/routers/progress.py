"""Progress Router - Handles user progress tracking and analytics."""

from fastapi import APIRouter, HTTPException
from typing import List
from datetime import UTC, datetime, timedelta
from collections import defaultdict

from models.progress import (
    UserProgress,
    get_user_stats,
    get_all_user_progress,
    get_completed_courses,
)
from models.course import Course, Topic
from models.challenge import Challenge
from database import get_session

router = APIRouter()


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


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

        def _status_for(challenge_id: str) -> str:
            progress = progress_map.get(challenge_id)
            return progress.status if progress else "unseen"
        
        # Calculate stats
        total = len(challenges)
        passed = sum(1 for c in challenges if _status_for(c.id) == "passed")
        attempted = sum(1 for c in challenges if _status_for(c.id) == "attempted")
        skipped = sum(1 for c in challenges if _status_for(c.id) == "skipped")
        unseen = total - passed - attempted - skipped
        completion_pct = round(passed / total * 100, 1) if total > 0 else 0
        estimated_time_remaining_minutes = max(unseen, 0) * 15
        
        return {
            "course_id": course_id,
            "course_title": course.title,
            "total_challenges": total,
            "passed": passed,
            "attempted": attempted,
            "skipped": skipped,
            "unseen": unseen,
            "completion_pct": completion_pct,
            # Compatibility fields for frontend consumers
            "completed_challenges": passed,
            "skipped_challenges": skipped,
            "completion_percentage": completion_pct,
            "estimated_time_remaining_minutes": estimated_time_remaining_minutes,
        }
    finally:
        session.close()


@router.get("/weak-topics")
async def get_weak_topics(user_id: str = "default", threshold: float = 0.6):
    """Get topics with pass rate below threshold."""
    if threshold < 0 or threshold > 1:
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")

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
                    topic = session.get(Topic, topic_id)
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


@router.get("/stats")
async def get_progress_stats(user_id: str = "default"):
    """Get dashboard-friendly progress statistics for a user."""
    session = next(get_session())
    try:
        all_progress = get_all_user_progress(session, user_id)
        challenge_progress = [p for p in all_progress if p.challenge_id]

        total_challenges_completed = sum(1 for p in challenge_progress if p.status == "passed")
        total_attempts = sum(max(1, p.attempts) for p in challenge_progress)
        success_rate = round((total_challenges_completed / total_attempts) * 100, 1) if total_attempts > 0 else 0.0

        # Estimate of total learning time in minutes (coarse, but useful for dashboards)
        total_time_spent = total_attempts * 15

        challenge_ids = [p.challenge_id for p in challenge_progress if p.challenge_id]
        challenges = session.query(Challenge).filter(Challenge.id.in_(challenge_ids)).all() if challenge_ids else []
        challenge_map = {c.id: c for c in challenges}

        challenges_by_difficulty = {"easy": 0, "medium": 0, "hard": 0}
        challenges_by_type = {"command": 0, "output": 0, "file": 0}

        for p in challenge_progress:
            challenge = challenge_map.get(p.challenge_id)
            if not challenge:
                continue

            if challenge.difficulty in challenges_by_difficulty:
                challenges_by_difficulty[challenge.difficulty] += 1
            if challenge.type in challenges_by_type:
                challenges_by_type[challenge.type] += 1

        topic_stats = defaultdict(lambda: {"total": 0, "passed": 0})
        for p in challenge_progress:
            if p.topic_id:
                topic_stats[p.topic_id]["total"] += 1
                if p.status == "passed":
                    topic_stats[p.topic_id]["passed"] += 1

        weak_areas = []
        for topic_id, stats in topic_stats.items():
            if stats["total"] <= 0:
                continue

            success = stats["passed"] / stats["total"]
            if success < 0.7:
                topic = session.get(Topic, topic_id)
                weak_areas.append(
                    {
                        "topic": topic.name if topic else "Unknown",
                        "successRate": round(success * 100, 1),
                        "attempts": stats["total"],
                    }
                )

        weak_areas.sort(key=lambda x: x["successRate"])

        active_days = {
            (p.last_attempted_at or p.passed_at).date()
            for p in challenge_progress
            if (p.last_attempted_at or p.passed_at)
        }

        today = _utc_now().date()
        day = today if today in active_days else today - timedelta(days=1)
        current_streak = 0
        while day in active_days:
            current_streak += 1
            day -= timedelta(days=1)

        return {
            "totalChallengesCompleted": total_challenges_completed,
            "currentStreak": current_streak,
            "successRate": success_rate,
            "totalTimeSpent": total_time_spent,
            "challengesByDifficulty": challenges_by_difficulty,
            "challengesByType": challenges_by_type,
            "weakAreas": weak_areas,
        }
    finally:
        session.close()


@router.get("/activity")
async def get_activity_heatmap(user_id: str = "default", days: int = 365):
    """Get daily activity counts for heatmap rendering."""
    if days < 1 or days > 730:
        raise HTTPException(status_code=400, detail="days must be between 1 and 730")

    session = next(get_session())
    try:
        all_progress = get_all_user_progress(session, user_id)
        challenge_progress = [p for p in all_progress if p.challenge_id]

        start_date = _utc_now().date() - timedelta(days=days - 1)
        daily_counts = defaultdict(int)

        for p in challenge_progress:
            activity_dt = p.last_attempted_at or p.passed_at
            if not activity_dt:
                continue

            activity_date = activity_dt.date()
            if activity_date >= start_date:
                daily_counts[activity_date.isoformat()] += max(1, p.attempts)

        return [
            {"date": date_str, "count": count}
            for date_str, count in sorted(daily_counts.items())
        ]
    finally:
        session.close()
