#!/usr/bin/env python3
"""
Test script to verify routes are properly registered
"""

import sys
import os

# Add backend to path
sys.path.insert(0, '/root/cyberlab/backend')

def test_routes():
    print("Testing route registration...")
    
    # Import the router directly
    from routers.grinder import router
    print(f"\nRoutes in grinder router ({len(router.routes)} total):")
    for i, route in enumerate(router.routes):
        print(f"  {i+1}. {getattr(route, 'path', 'NO_PATH_ATTR')}")
    
    # Import the app
    from main import app
    print(f"\nRoutes in main app ({len(app.routes)} total):")
    grinder_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and 'grinder' in getattr(route, 'path', ''):
            grinder_routes.append(route.path)
            print(f"  Found: {route.path}")
    
    print(f"\nTotal grinder routes found in app: {len(grinder_routes)}")
    
    # Test direct API call
    print("\nTesting API endpoints...")
    import requests
    
    try:
        # Test the jobs endpoint
        response = requests.options('http://192.168.0.204:8080/api/grinder/jobs')
        print(f"OPTIONS /api/grinder/jobs: {response.status_code}")
    except Exception as e:
        print(f"OPTIONS /api/grinder/jobs failed: {e}")
    
    try:
        # Test openapi
        response = requests.get('http://192.168.0.204:8080/openapi.json')
        if response.status_code == 200:
            data = response.json()
            paths = [path for path in data['paths'].keys() if 'grinder' in path]
            print(f"\nOpenAPI grinder paths ({len(paths)}):")
            for path in sorted(paths):
                print(f"  {path}")
    except Exception as e:
        print(f"OpenAPI test failed: {e}")

if __name__ == "__main__":
    test_routes()