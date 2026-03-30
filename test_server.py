#!/usr/bin/env python3
"""Test script that creates the exact same app as main.py"""
import sys

if __name__ != "__main__" and "pytest" in sys.modules:
    import pytest

    pytest.skip("manual smoke script; excluded from automated pytest runs", allow_module_level=True)

sys.path.insert(0, '/root/cyberlab/backend')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import create_db_and_tables
from routers import courses, challenges, grinder, progress

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting CyberLab backend...")
    create_db_and_tables()
    print("✅ Database initialized")
    yield
    print("👋 Shutting down CyberLab backend...")

app = FastAPI(
    title="CyberLab",
    description="Interactive cybersecurity learning platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://192.168.0.204:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with /api prefix
print(f"DEBUG: About to include grinder router with {len(grinder.routes)} routes")
for route in grinder.routes:
    print(f"DEBUG:   Grinder route: {getattr(route, 'path', 'NO_PATH')}")
    
app.include_router(courses, prefix="/api/courses", tags=["courses"])
app.include_router(challenges, prefix="/api/challenges", tags=["challenges"])
app.include_router(grinder, prefix="/api/grinder", tags=["grinder"])
app.include_router(progress, prefix="/api/progress", tags=["progress"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "CyberLab"}

# Print all routes after inclusion
print(f"DEBUG: App has {len(app.routes)} total routes")
grinder_paths = [r.path for r in app.routes if hasattr(r, 'path') and 'grinder' in r.path]
print(f"DEBUG: Grinder paths in final app: {grinder_paths}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")