#!/usr/bin/env python3
"""
Alternative server startup to ensure all routes are loaded correctly
"""
import sys
import os
from pathlib import Path

# Ensure imports resolve from the current backend directory
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
import uvicorn

if __name__ == "__main__":
    print("Starting server with verified routes...")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")