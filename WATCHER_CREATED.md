# File Watcher Service Created

**Created:** 2026-03-23 14:39 UTC

## Files Created

### `/root/.openclaw/cyberlab/backend/watcher.py`
File system watcher service using watchdog library.

**Features:**
- Watches `./drop/` directory for new PDF/PPTX files
- On new file: computes SHA256 hash, checks if already processed (via Course.source_hash)
- If new: triggers `grinder.process_file()`
- Logs all actions with timestamps
- Handles file move events (user drops file into directory)
- Configurable via environment variables

**Environment Variables:**
- `WATCH_PATH` - Directory to watch (default: `./drop`)
- `CHECK_INTERVAL` - Polling interval in seconds (default: `1`)

**Usage:**
```bash
cd /root/.openclaw/cyberlab/backend
python watcher.py
```

**Or with custom config:**
```bash
WATCH_PATH=/path/to/drop CHECK_INTERVAL=2 python watcher.py
```

## Files Modified

### `/root/.openclaw/cyberlab/backend/requirements.txt`
Added `watchdog>=3.0.0` dependency.

## Installation

Before running the watcher:
```bash
cd /root/.openclaw/cyberlab/backend
pip install -r requirements.txt
```

## Notes

- The watcher runs asynchronously and processes files as they appear
- Duplicate detection uses SHA256 hash of source files
- Files are checked against the `Course.source_hash` database field
- Processing errors are logged but don't crash the watcher
