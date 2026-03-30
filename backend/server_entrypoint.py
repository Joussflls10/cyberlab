#!/usr/bin/env python3
"""
Server entrypoint to ensure proper route registration
"""
import sys
from pathlib import Path

# Add the backend to the path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from routers import grinder

# Print all routes as a final verification
print("FINAL VERIFICATION OF ROUTES:")
print(f"Grinder router has {len(grinder.routes)} routes:")
for i, route in enumerate(grinder.routes):
    path = getattr(route, 'path', 'NO_PATH')
    methods = getattr(route, 'methods', 'NO_METHODS')
    print(f"  {i}: {path} - {methods}")

# Print what's in the main app
print(f"\nMain app has {len(app.routes)} total routes")
grinder_app_routes = [r for r in app.routes if hasattr(r, 'path') and 'grinder' in r.path]
print(f"Grinder routes in main app ({len(grinder_app_routes)}):")
for route in grinder_app_routes:
    path = getattr(route, 'path', 'NO_PATH')
    methods = getattr(route, 'methods', 'NO_METHODS')
    print(f"  {path} - {methods}")

if __name__ == "__main__":
    import uvicorn
    print("\nStarting server...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
        reload=False  # Disable reload to prevent caching issues
    )