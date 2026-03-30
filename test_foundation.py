#!/usr/bin/env python3
"""
Foundation Smoke Test for CyberLab
Verifies database schema and sandbox functionality before building higher layers.
"""

import sys
import os
import hashlib
from datetime import datetime

if __name__ != "__main__" and "pytest" in sys.modules:
    import pytest

    pytest.skip("manual smoke script; excluded from automated pytest runs", allow_module_level=True)

# Set up paths
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

print("=" * 60)
print("CYBERLAB FOUNDATION SMOKE TEST")
print("=" * 60)

# Test 1: Database imports and table creation
print("\n[1/6] Testing database imports...")
try:
    # Import directly to avoid relative import issues
    from sqlmodel import SQLModel, create_engine, Session, Field, Relationship
    from sqlalchemy.orm import sessionmaker
    
    # Import models
    from models.course import Course, Topic
    from models.challenge import Challenge
    from models.progress import UserProgress
    
    print("✅ All model imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Create engine and tables
print("\n[2/6] Creating database tables...")
try:
    # Use test database
    engine = create_engine(
        "sqlite:///./test_foundation.db",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)
    print("✅ Tables created successfully")
except Exception as e:
    print(f"❌ Table creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Insert Course with string ID
print("\n[3/6] Testing Course insert with SHA256-style ID...")
course_id = None
try:
    session = SessionLocal()
    course_id = hashlib.sha256(b"test_course").hexdigest()
    course = Course(
        id=course_id,
        title="Test Course",
        description="A test course",
        source_file="test.pdf",
        source_hash=hashlib.sha256(b"file_content").hexdigest(),
    )
    session.add(course)
    session.commit()
    session.refresh(course)
    
    assert isinstance(course.id, str), f"Course ID should be str, got {type(course.id)}"
    assert len(course.id) == 64, "Course ID should be 64 char SHA256"
    print(f"✅ Course inserted with ID: {course.id[:16]}...")
    session.close()
except Exception as e:
    print(f"❌ Course insert failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Insert Topic with string ID
print("\n[4/6] Testing Topic insert...")
topic_id = None
try:
    session = SessionLocal()
    topic_id = hashlib.sha256(b"test_topic").hexdigest()
    topic = Topic(
        id=topic_id,
        course_id=course_id,
        name="Test Topic",
        order=1,
    )
    session.add(topic)
    session.commit()
    session.refresh(topic)
    
    assert isinstance(topic.id, str), f"Topic ID should be str, got {type(topic.id)}"
    print(f"✅ Topic inserted with ID: {topic.id[:16]}...")
    session.close()
except Exception as e:
    print(f"❌ Topic insert failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Insert Challenge with SHA256 ID (critical test)
print("\n[5/6] Testing Challenge insert with computed SHA256 ID...")
challenge_id = None
try:
    session = SessionLocal()
    question = "What is the output of echo hello?"
    validation_script = "#!/bin/bash\necho hello"
    challenge_id_input = f"{question}{validation_script}{topic_id}"
    challenge_id = hashlib.sha256(challenge_id_input.encode()).hexdigest()
    
    challenge = Challenge(
        id=challenge_id,
        course_id=course_id,
        topic_id=topic_id,
        type="output",
        question=question,
        sandbox_image="rocky9-base",
        validation_script=validation_script,
        expected_output="hello",
        difficulty="easy",
        order=1,
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    
    assert isinstance(challenge.id, str), f"Challenge ID should be str, got {type(challenge.id)}"
    assert len(challenge.id) == 64, "Challenge ID should be 64 char SHA256"
    print(f"✅ Challenge inserted with SHA256 ID: {challenge.id[:16]}...")
    
    # Verify we can query it back
    queried = session.get(Challenge, challenge_id)
    assert queried is not None, "Challenge should be queryable by ID"
    assert queried.question == question, "Question should match"
    print(f"✅ Challenge query-by-ID works")
    session.close()
except Exception as e:
    print(f"❌ Challenge insert failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Sandbox service imports
print("\n[6/6] Testing sandbox service imports...")
try:
    from services.sandbox import start_sandbox, stop_sandbox, run_validation, cleanup_orphaned_containers
    print("✅ Sandbox service imports successful")
    print("   (Note: Actual container tests require Docker daemon)")
except Exception as e:
    print(f"❌ Sandbox import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL TESTS PASSED ✅")
print("=" * 60)
print("\nFoundation is solid. Ready to build:")
print("  - FastAPI main.py and routers")
print("  - Grinder endpoint")
print("  - Challenge endpoints")
print("  - Frontend")

# Cleanup test database
os.remove("./test_foundation.db")
print("\nCleaned up test database.")
