"""ImportJob model for tracking async file processing."""

from typing import List, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
import json


class ImportJob(SQLModel, table=True):
    """Tracks asynchronous file import jobs."""
    
    __tablename__ = "import_jobs"
    
    id: str = Field(primary_key=True)
    file_path: str
    status: str = Field(default="pending")  # pending, processing, completed, error
    course_id: Optional[str] = Field(default=None)
    progress_percent: int = Field(default=0)
    logs: str = Field(default="[]")  # JSON array of log strings
    error_message: Optional[str] = Field(default=None)
    topics_count: int = Field(default=0)
    challenges_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    
    def add_log(self, message: str, level: str = "info") -> None:
        """Add a log entry with timestamp."""
        logs_list = json.loads(self.logs)
        timestamp = datetime.utcnow().isoformat()
        logs_list.append(f"[{timestamp}] [{level.upper()}] {message}")
        # Keep last 1000 log lines to prevent unbounded growth
        logs_list = logs_list[-1000:]
        self.logs = json.dumps(logs_list)
        self.updated_at = datetime.utcnow()
    
    def get_logs(self) -> List[str]:
        """Get logs as a list of strings."""
        return json.loads(self.logs)
    
    def update_progress(self, percent: int) -> None:
        """Update progress percentage."""
        self.progress_percent = min(100, max(0, percent))
        self.updated_at = datetime.utcnow()
