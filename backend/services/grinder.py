"""CyberLab Content Grinder - Full Ingestion Pipeline."""

import hashlib
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

import fitz  # pymupdf
from pptx import Presentation
from sqlmodel import Session, select

from database import engine
from .ai_client import get_client, parse_json_response

# Import models - NEVER define new tables here
from models.course import Course, Topic
from models.challenge import Challenge
from models.import_job import ImportJob

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration per spec
MAX_CHUNK_TOKENS = 6000
CHALLENGES_CACHE_DIR = Path("challenges")
MAX_CONCURRENT_JOBS = 3

# Global semaphore to limit concurrent processing
_job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


def compute_source_hash(file_path: str) -> str:
    """Compute SHA256 hash of file for duplicate detection."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_challenge_id(question: str, validation_script: str, topic_id: str) -> str:
    """Compute SHA256 hash for challenge deduplication per spec."""
    content = f"{question}{validation_script}{topic_id}"
    return hashlib.sha256(content.encode()).hexdigest()


def parse_pdf(file_path: str) -> str:
    """Extract text from PDF using pymupdf."""
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text()
        doc.close()
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        raise
    return text


def parse_pptx(file_path: str) -> str:
    """Extract text from PowerPoint using python-pptx."""
    text = ""
    try:
        prs = Presentation(file_path)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
                if shape.has_notes_slide:
                    text += shape.notes_slide.notes_text_frame.text + "\n"
    except Exception as e:
        logger.error(f"Failed to parse PPTX {file_path}: {e}")
        raise
    return text


def chunk_text(text: str, max_tokens: int = 6000) -> List[str]:
    """Chunk text at ~6000 tokens (approx 24000 chars)."""
    max_chars = max_tokens * 4
    chunks = []
    current_chunk = ""
    
    for paragraph in text.split("\n\n"):
        if len(current_chunk) + len(paragraph) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = paragraph
        else:
            current_chunk += "\n\n" + paragraph
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


async def extract_topics(text: str) -> Dict[str, Any]:
    """Extract topics from course text using DeepSeek V3."""
    client = get_client()
    
    system_prompt = """You are a curriculum analyst. Extract structured learning topics from course material.
Return ONLY valid JSON. No markdown, no preamble, no explanation."""
    
    user_prompt = f"""Analyze this course material and extract all distinct topics and subtopics.
For each topic, list the key commands, tools, or procedures covered.

Return this exact JSON structure:
{{
 "course_name": "inferred name of the course",
 "topics": [
   {{
     "name": "Topic name",
     "order": 1,
     "key_concepts": ["concept1", "concept2"],
     "tools_mentioned": ["ansible", "wazuh"],
     "commands_mentioned": ["ansible-playbook", "systemctl"],
     "procedures": ["step-by-step procedure descriptions extracted verbatim"]
   }}
 ]
}}

Course material:
{text[:8000]}"""
    
    try:
        response = await client.call_model("grinder", system_prompt, user_prompt, max_tokens=4000)
        return parse_json_response(response)
    except Exception as e:
        logger.error(f"Failed to extract topics: {e}")
        raise


async def generate_challenges(topic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate challenges for a topic using DeepSeek V3."""
    client = get_client()
    
    topic_name = topic_data.get("name", "Unknown Topic")
    key_concepts = topic_data.get("key_concepts", [])
    tools = topic_data.get("tools_mentioned", [])
    commands = topic_data.get("commands_mentioned", [])
    procedures = topic_data.get("procedures", [])
    
    system_prompt = """You are a cybersecurity instructor designing hands-on lab challenges.
Return ONLY valid JSON. No markdown, no preamble, no explanation."""
    
    user_prompt = f"""Generate practical, hands-on challenges for this topic. 
Challenges must test actual command execution, not just knowledge recall.

Topic: {topic_name}
Key concepts: {key_concepts}
Tools: {tools}
Commands: {commands}
Procedures: {procedures}

For each challenge, determine:
- type: "command" (student runs a command), "file" (student creates/modifies a file), or "output" (student runs command and output is checked)
- sandbox_image: one of ["rocky9-base", "ubuntu-wazuh", "kali-base"] — pick what makes sense
- validation_script: a bash script that exits 0 if correct, exits 1 if wrong. This runs inside the container after the student submits.

Return this exact JSON:
{{
 "challenges": [
   {{
     "question": "Clear, specific instruction of what to do",
     "hint": "Optional helpful hint or null",
     "type": "command",
     "sandbox_image": "rocky9-base",
     "difficulty": "easy",
     "validation_script": "#!/bin/bash\\n# check if ansible is installed\\nansible --version > /dev/null 2>&1 && exit 0 || exit 1",
     "expected_output": null
   }}
 ]
}}

Generate between 3 and 8 challenges per topic. Make them progressively harder."""
    
    try:
        response = await client.call_model("challenge_gen", system_prompt, user_prompt, max_tokens=4000)
        data = parse_json_response(response)
        return data.get("challenges", [])
    except Exception as e:
        logger.error(f"Failed to generate challenges: {e}")
        raise


async def review_validation_script(question: str, script: str, sandbox_image: str) -> Dict[str, Any]:
    """Review validation script using Qwen3 Coder."""
    client = get_client()
    
    system_prompt = """You are a bash script reviewer. Return ONLY valid JSON."""
    
    user_prompt = f"""Review this bash validation script for a lab challenge.
The script runs inside a Docker container after a student completes a task.
It should exit 0 on success, exit 1 on failure.

Question: {question}
Script: {script}
Container image: {sandbox_image}

Is this script correct and will it reliably validate the student's work?
Return JSON: {{"valid": true/false, "issues": "description or null", "fixed_script": "corrected script or null"}}"""
    
    try:
        response = await client.call_model("validator_review", system_prompt, user_prompt, max_tokens=2000)
        return parse_json_response(response)
    except Exception as e:
        logger.error(f"Failed to review validation script: {e}")
        return {"valid": True, "issues": None, "fixed_script": None}


def save_challenge_cache(course_id: str, topic_slug: str, challenges: List[Dict[str, Any]]) -> None:
    """Save challenge cache to disk."""
    CHALLENGES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    course_dir = CHALLENGES_CACHE_DIR / course_id
    course_dir.mkdir(exist_ok=True)
    
    cache_file = course_dir / f"{topic_slug}.json"
    with open(cache_file, "w") as f:
        json.dump(challenges, f, indent=2)


def load_challenge_cache(course_id: str, topic_slug: str) -> Optional[List[Dict[str, Any]]]:
    """Load challenge cache from disk."""
    cache_file = CHALLENGES_CACHE_DIR / course_id / f"{topic_slug}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    return None


def _update_job_progress(job_id: str, percent: int) -> None:
    """Update job progress in database."""
    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.update_progress(percent)
            session.commit()


def _add_job_log(job_id: str, message: str, level: str = "info") -> None:
    """Add log entry to job."""
    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.add_log(message, level)
            session.commit()


def _update_job_status(job_id: str, status: str, course_id: Optional[str] = None, 
                        error_message: Optional[str] = None) -> None:
    """Update job status in database."""
    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.status = status
            if course_id:
                job.course_id = course_id
            if error_message:
                job.error_message = error_message
            if status in ["completed", "error"]:
                job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            session.commit()


def _update_job_counts(job_id: str, topics_count: int, challenges_count: int) -> None:
    """Update job counts in database."""
    with Session(engine) as session:
        job = session.get(ImportJob, job_id)
        if job:
            job.topics_count = topics_count
            job.challenges_count = challenges_count
            session.commit()


async def process_file_with_job(job_id: str, file_path: str) -> None:
    """Process a file with job tracking and progress updates."""
    async with _job_semaphore:
        try:
            _update_job_status(job_id, "processing")
            _add_job_log(job_id, f"Starting processing of {Path(file_path).name}")
            
            # Step 1: Compute source hash and check for duplicates (0-5%)
            _add_job_log(job_id, "Computing file hash for duplicate detection...")
            source_hash = compute_source_hash(file_path)
            
            with Session(engine) as session:
                existing = session.exec(select(Course).where(Course.source_hash == source_hash)).first()
                if existing:
                    # Check if course has content - if not, delete and reprocess
                    if existing.topic_count == 0 or existing.challenge_count == 0:
                        _add_job_log(job_id, f"Found empty course '{existing.title}' - deleting and reprocessing", "warn")
                        session.delete(existing)
                        session.commit()
                        _add_job_log(job_id, "Deleted empty course, starting fresh processing...")
                    else:
                        _add_job_log(job_id, f"File already processed as course: {existing.title}", "info")
                        _update_job_status(job_id, "completed", course_id=existing.id)
                        _update_job_progress(job_id, 100)
                        return
            
            _update_job_progress(job_id, 5)
            
            # Step 2: Parse file (5-15%)
            _add_job_log(job_id, "Parsing document...")
            if file_path.lower().endswith(".pdf"):
                text = parse_pdf(file_path)
            elif file_path.lower().endswith(".pptx"):
                text = parse_pptx(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_path}")
            
            _add_job_log(job_id, f"Extracted {len(text)} characters from document")
            _update_job_progress(job_id, 15)
            
            # Step 3: Extract topics (15-40%)
            _add_job_log(job_id, "Extracting topics with AI...")
            topics_data = await extract_topics(text)
            course_name = topics_data.get("course_name", "Unknown Course")
            topics = topics_data.get("topics", [])
            
            _add_job_log(job_id, f"Found {len(topics)} topics in course: {course_name}")
            _update_job_progress(job_id, 40)
            
            # Step 4: Create course
            course_id = str(uuid.uuid4())
            with Session(engine) as session:
                course = Course(
                    id=course_id,
                    title=course_name,
                    description=f"Auto-generated from {Path(file_path).name}",
                    source_file=Path(file_path).name,
                    source_hash=source_hash,
                )
                session.add(course)
                session.commit()
            
            _add_job_log(job_id, f"Created course: {course_name}")
            
            # Step 5: Process each topic (40-90%)
            total_challenges = 0
            topic_progress_increment = 50 / len(topics) if topics else 50
            
            for idx, topic_data in enumerate(topics):
                topic_name = topic_data.get("name", "Unknown Topic")
                topic_order = topic_data.get("order", idx + 1)
                
                _add_job_log(job_id, f"Processing topic {idx + 1}/{len(topics)}: {topic_name}")
                
                # Create topic
                topic_id = str(uuid.uuid4())
                with Session(engine) as session:
                    topic = Topic(
                        id=topic_id,
                        course_id=course_id,
                        name=topic_name,
                        order=topic_order,
                    )
                    session.add(topic)
                    session.commit()
                
                # Generate challenges
                try:
                    challenges_data = await generate_challenges(topic_data)
                    _add_job_log(job_id, f"Generated {len(challenges_data)} challenges for {topic_name}")
                except Exception as e:
                    _add_job_log(job_id, f"Failed to generate challenges for {topic_name}: {e}", "error")
                    continue
                
                # Process each challenge
                for challenge_data in challenges_data:
                    question = challenge_data.get("question", "")
                    validation_script = challenge_data.get("validation_script", "")
                    
                    # Compute deterministic challenge ID
                    challenge_id = compute_challenge_id(question, validation_script, topic_id)
                    
                    # Check if challenge already exists
                    with Session(engine) as session:
                        existing_challenge = session.get(Challenge, challenge_id)
                        if existing_challenge:
                            continue
                    
                    # Review validation script
                    try:
                        review = await review_validation_script(
                            question, validation_script, challenge_data.get("sandbox_image", "rocky9-base")
                        )
                        if review.get("valid") and review.get("fixed_script"):
                            validation_script = review["fixed_script"]
                    except Exception as e:
                        _add_job_log(job_id, f"Validation script review failed: {e}", "warn")
                    
                    # Create challenge
                    with Session(engine) as session:
                        challenge = Challenge(
                            id=challenge_id,
                            course_id=course_id,
                            topic_id=topic_id,
                            type=challenge_data.get("type", "command"),
                            question=question,
                            hint=challenge_data.get("hint"),
                            sandbox_image=challenge_data.get("sandbox_image", "rocky9-base"),
                            validation_script=validation_script,
                            expected_output=challenge_data.get("expected_output"),
                            difficulty=challenge_data.get("difficulty", "easy"),
                            order=challenge_data.get("order", 0),
                        )
                        session.add(challenge)
                        session.commit()
                        total_challenges += 1
                
                # Save cache
                topic_slug = topic_name.lower().replace(" ", "-").replace("_", "-")[:50]
                save_challenge_cache(course_id, topic_slug, challenges_data)
                
                # Update progress per topic
                current_progress = 40 + int((idx + 1) * topic_progress_increment)
                _update_job_progress(job_id, min(current_progress, 90))
            
            # Step 6: Update course counts (90-100%)
            with Session(engine) as session:
                course = session.get(Course, course_id)
                if course:
                    course.topic_count = len(topics)
                    course.challenge_count = total_challenges
                    session.commit()
            
            _update_job_counts(job_id, len(topics), total_challenges)
            _add_job_log(job_id, f"Processing complete: {len(topics)} topics, {total_challenges} challenges")
            _update_job_progress(job_id, 100)
            _update_job_status(job_id, "completed", course_id=course_id)
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing job {job_id}: {error_msg}")
            _add_job_log(job_id, f"Processing failed: {error_msg}", "error")
            _update_job_status(job_id, "error", error_message=error_msg)
            raise


async def process_file(file_path: str) -> Dict[str, Any]:
    """Main entry point: process a course file end-to-end (sync version for backwards compatibility)."""
    logger.info(f"Processing file: {file_path}")
    
    # Step 1: Compute source hash and check for duplicates
    source_hash = compute_source_hash(file_path)
    
    with Session(engine) as session:
        existing = session.exec(select(Course).where(Course.source_hash == source_hash)).first()
        if existing:
            # Check if course has content - if not, delete and reprocess
            if existing.topic_count == 0 or existing.challenge_count == 0:
                logger.info(f"Found empty course '{existing.title}' - deleting and reprocessing")
                session.delete(existing)
                session.commit()
                logger.info("Deleted empty course, starting fresh processing...")
            else:
                logger.info(f"File already processed: {existing.id}")
                return {"course_id": existing.id, "status": "already_processed"}
    
    # Step 2: Parse file
    if file_path.lower().endswith(".pdf"):
        text = parse_pdf(file_path)
    elif file_path.lower().endswith(".pptx"):
        text = parse_pptx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")
    
    # Step 3: Extract topics
    logger.info("Extracting topics...")
    topics_data = await extract_topics(text)
    course_name = topics_data.get("course_name", "Unknown Course")
    topics = topics_data.get("topics", [])
    
    # Step 4: Create course
    course_id = str(uuid.uuid4())
    with Session(engine) as session:
        course = Course(
            id=course_id,
            title=course_name,
            description=f"Auto-generated from {Path(file_path).name}",
            source_file=Path(file_path).name,
            source_hash=source_hash,
        )
        session.add(course)
        session.commit()
    
    # Step 5: Process each topic
    total_challenges = 0
    for topic_data in topics:
        topic_name = topic_data.get("name", "Unknown Topic")
        topic_order = topic_data.get("order", 0)
        
        logger.info(f"Processing topic: {topic_name}")
        
        # Create topic
        topic_id = str(uuid.uuid4())
        with Session(engine) as session:
            topic = Topic(
                id=topic_id,
                course_id=course_id,
                name=topic_name,
                order=topic_order,
            )
            session.add(topic)
            session.commit()
        
        # Generate challenges
        try:
            challenges_data = await generate_challenges(topic_data)
        except Exception as e:
            logger.error(f"Failed to generate challenges for {topic_name}: {e}")
            continue
        
        # Process each challenge
        for challenge_data in challenges_data:
            question = challenge_data.get("question", "")
            validation_script = challenge_data.get("validation_script", "")
            
            # Compute deterministic challenge ID
            challenge_id = compute_challenge_id(question, validation_script, topic_id)
            
            # Check if challenge already exists
            with Session(engine) as session:
                existing_challenge = session.get(Challenge, challenge_id)
                if existing_challenge:
                    logger.info(f"Challenge already exists: {challenge_id[:16]}...")
                    continue
            
            # Review validation script
            try:
                review = await review_validation_script(
                    question, validation_script, challenge_data.get("sandbox_image", "rocky9-base")
                )
                if review.get("valid") and review.get("fixed_script"):
                    validation_script = review["fixed_script"]
            except Exception as e:
                logger.warning(f"Validation script review failed: {e}")
            
            # Create challenge
            with Session(engine) as session:
                challenge = Challenge(
                    id=challenge_id,
                    course_id=course_id,
                    topic_id=topic_id,
                    type=challenge_data.get("type", "command"),
                    question=question,
                    hint=challenge_data.get("hint"),
                    sandbox_image=challenge_data.get("sandbox_image", "rocky9-base"),
                    validation_script=validation_script,
                    expected_output=challenge_data.get("expected_output"),
                    difficulty=challenge_data.get("difficulty", "easy"),
                    order=challenge_data.get("order", 0),
                )
                session.add(challenge)
                session.commit()
                total_challenges += 1
        
        # Save cache
        topic_slug = topic_name.lower().replace(" ", "-").replace("_", "-")[:50]
        save_challenge_cache(course_id, topic_slug, challenges_data)
    
    # Update course counts
    with Session(engine) as session:
        course = session.get(Course, course_id)
        if course:
            course.topic_count = len(topics)
            course.challenge_count = total_challenges
            session.commit()
    
    logger.info(f"Processing complete: {len(topics)} topics, {total_challenges} challenges")
    
    return {
        "course_id": course_id,
        "course_name": course_name,
        "topics_count": len(topics),
        "challenges_count": total_challenges,
        "status": "success",
    }


def get_queue_status() -> Dict[str, Any]:
    """Get grinder queue status."""
    return {
        "status": "idle",
        "queue_length": 0,
        "last_processed": None,
    }
