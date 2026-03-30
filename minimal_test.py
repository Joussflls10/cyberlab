#!/usr/bin/env python3
"""
Minimal test to verify the jobs endpoint works
"""

import sys

if __name__ != "__main__" and "pytest" in sys.modules:
    import pytest

    pytest.skip("manual smoke script; excluded from automated pytest runs", allow_module_level=True)

from fastapi import FastAPI, File, UploadFile
import uuid
import os

app = FastAPI()

UPLOAD_DIR = "/root/.openclaw/cyberlab/drop"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/grinder/jobs")
async def create_import_job(file: UploadFile = File(...)):
    """Test endpoint to see if it works"""
    return {"success": True, "job_id": str(uuid.uuid4()), "message": "Test endpoint working"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)