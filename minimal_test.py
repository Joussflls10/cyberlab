#!/usr/bin/env python3
"""
Minimal test to verify the jobs endpoint works
"""

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uuid
from sqlmodel import SQLModel, Session, create_engine, select
from models.import_job import ImportJob
from database import engine
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