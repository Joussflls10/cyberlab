"""
CyberLab File Watcher Service
Monitors drop directory for new PDF/PPTX files and triggers processing pipeline.
"""

import os
import sys
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, select
from database import engine
from models import Course
from services.grinder import compute_source_hash, process_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration via environment variables
WATCH_PATH = os.getenv('WATCH_PATH', './drop')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1'))  # seconds

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.pdf', '.pptx', '.ppt'}


def is_supported_file(file_path: str) -> bool:
    """Check if file has a supported extension."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def is_already_processed(file_path: str) -> bool:
    """Check if file has already been processed by computing its hash."""
    try:
        source_hash = compute_source_hash(file_path)
        with Session(engine) as session:
            existing = session.exec(select(Course).where(Course.source_hash == source_hash)).first()
            if existing:
                logger.info(f"File already processed (Course ID: {existing.id}, Hash: {source_hash[:16]}...)")
                return True
    except Exception as e:
        logger.error(f"Error checking if file is processed: {e}")
    return False


async def process_new_file(file_path: str):
    """Process a new file through the grinder pipeline."""
    logger.info(f"Starting processing of: {file_path}")
    try:
        result = await process_file(file_path, engine)
        logger.info(f"Processing complete: {result}")
    except Exception as e:
        logger.error(f"Error processing file {file_path}: {e}")


class DropDirectoryHandler(FileSystemEventHandler):
    """Handle file system events in the drop directory."""
    
    def __init__(self):
        super().__init__()
        self.processing_queue = set()
    
    def _should_process(self, file_path: str) -> bool:
        """Determine if file should be processed."""
        # Check if it's a supported file type
        if not is_supported_file(file_path):
            logger.debug(f"Ignoring unsupported file: {file_path}")
            return False
        
        # Check if already in processing queue
        if file_path in self.processing_queue:
            logger.debug(f"File already in queue: {file_path}")
            return False
        
        # Check if already processed
        if is_already_processed(file_path):
            return False
        
        return True
    
    def _handle_file(self, file_path: str):
        """Handle a file event (created or moved)."""
        # Wait a bit to ensure file is fully written
        time.sleep(0.5)
        
        if not Path(file_path).exists():
            logger.warning(f"File no longer exists: {file_path}")
            return
        
        if not self._should_process(file_path):
            return
        
        # Add to processing queue
        self.processing_queue.add(file_path)
        
        try:
            logger.info(f"New file detected: {file_path}")
            # Run async processing in a new event loop
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(process_new_file(file_path))
        except Exception as e:
            logger.error(f"Error handling file {file_path}: {e}")
        finally:
            # Remove from queue
            self.processing_queue.discard(file_path)
    
    def on_created(self, event):
        """Handle file creation events."""
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            logger.info(f"File created: {event.src_path}")
            self._handle_file(event.src_path)
    
    def on_moved(self, event):
        """Handle file move events (user drops file into directory)."""
        if isinstance(event, FileMovedEvent) and not event.is_directory:
            logger.info(f"File moved: {event.src_path} -> {event.dest_path}")
            self._handle_file(event.dest_path)


def start_watcher():
    """Start the file system watcher."""
    # Resolve watch path
    watch_path = Path(WATCH_PATH)
    if not watch_path.is_absolute():
        watch_path = Path(__file__).parent.parent / watch_path
    
    watch_path = watch_path.resolve()
    
    if not watch_path.exists():
        logger.error(f"Watch directory does not exist: {watch_path}")
        sys.exit(1)
    
    logger.info(f"Starting file watcher on: {watch_path}")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")
    logger.info(f"Supported extensions: {SUPPORTED_EXTENSIONS}")
    
    # Create event handler and observer
    event_handler = DropDirectoryHandler()
    observer = Observer(timeout=CHECK_INTERVAL)
    observer.schedule(event_handler, str(watch_path), recursive=False)
    
    # Start observer
    observer.start()
    logger.info("File watcher started successfully")
    
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Stopping file watcher...")
        observer.stop()
    
    observer.join()
    logger.info("File watcher stopped")


if __name__ == "__main__":
    start_watcher()
