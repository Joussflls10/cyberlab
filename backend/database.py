"""Database setup and session management for CyberLab."""

from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.orm import sessionmaker
from typing import Generator
from datetime import datetime

try:
    from config import get_settings
except ImportError:
    from .config import get_settings

settings = get_settings()

# Create engine with SQLite-specific configuration
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def create_db_and_tables() -> None:
    """Create all database tables."""
    SQLModel.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Initialize database with all tables."""
    try:
        from models import course, challenge, progress, import_job
    except ImportError:
        from .models import course, challenge, progress, import_job
    create_db_and_tables()


def cleanup_stalled_jobs() -> int:
    """Reset jobs stuck in 'processing' status to 'error' on startup.
    
    Returns the number of jobs that were reset.
    """
    try:
        from models.import_job import ImportJob
    except ImportError:
        from .models.import_job import ImportJob
    
    with Session(engine) as session:
        statement = select(ImportJob).where(ImportJob.status == "processing")
        stalled_jobs = session.exec(statement).all()
        
        count = 0
        for job in stalled_jobs:
            job.status = "error"
            job.error_message = "interrupted by restart"
            job.updated_at = datetime.utcnow()
            count += 1
        
        if count > 0:
            session.commit()
            print(f"🔄 Reset {count} stalled import jobs")
        
        return count
