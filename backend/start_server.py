#!/usr/bin/env python3
"""
Alternative server startup to ensure all routes are loaded correctly
"""
import sys
import os

# Ensure we're in the right directory
os.chdir('/root/cyberlab/backend')
sys.path.insert(0, '/root/cyberlab/backend')

from main import app
import uvicorn

if __name__ == "__main__":
    print("Starting server with verified routes...")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")