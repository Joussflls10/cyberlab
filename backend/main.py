"""CyberLab Backend - FastAPI Application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import create_db_and_tables, cleanup_stalled_jobs
from services.sandbox import cleanup_orphaned_containers
from routers import courses, challenges, grinder, progress


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 Starting CyberLab backend...")
    
    # Initialize database
    create_db_and_tables()
    print("✅ Database initialized")
    
    # Ensure sandbox network exists
    from services.sandbox import ensure_sandbox_network
    ensure_sandbox_network()
    print("✅ Sandbox network ready")
    
    # Cleanup orphaned containers (sync function, run in thread)
    import asyncio
    loop = asyncio.get_event_loop()
    cleanup_result = await loop.run_in_executor(None, cleanup_orphaned_containers)
    if cleanup_result.get("cleaned_count", 0) > 0:
        print(f"🧹 Cleaned up {cleanup_result['cleaned_count']} orphaned containers")
    
    # Reset stalled import jobs
    stalled_count = await loop.run_in_executor(None, cleanup_stalled_jobs)
    if stalled_count > 0:
        print(f"🔄 Reset {stalled_count} stalled import jobs")
    
    yield
    
    # Shutdown
    print("👋 Shutting down CyberLab backend...")


app = FastAPI(
    title="CyberLab",
    description="Interactive cybersecurity learning platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://192.168.0.204:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with /api prefix
app.include_router(courses, prefix="/api/courses", tags=["courses"])
app.include_router(challenges, prefix="/api/challenges", tags=["challenges"])
app.include_router(grinder, prefix="/api/grinder", tags=["grinder"])
app.include_router(progress, prefix="/api/progress", tags=["progress"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "CyberLab"}


if __name__ == "__main__":
    import uvicorn
    # Print routes for debugging
    print("DEBUG: Starting server with routes:")
    for route in app.routes:
        if hasattr(route, 'path') and 'grinder' in getattr(route, 'path', ''):
            methods = getattr(route, 'methods', 'NO_METHODS')
            print(f"  {getattr(route, 'path', 'NO_PATH')} -> {methods}")
    uvicorn.run(app, host="0.0.0.0", port=8080)
