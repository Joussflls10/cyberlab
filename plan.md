# CyberLab Build Plan

> Master plan document — updated after each build cycle.

## Current Status

| Step | Component | Status | Notes |
|------|-----------|--------|-------|
| 1 | Database + Models | ✅ Complete | SHA256 string PKs, correct schema |
| 2 | AI Client | ✅ Complete | OpenRouter wrapper with rate limiting |
| 3 | Grinder Service | ✅ Complete | PDF/PPTx → topics → challenges pipeline |
| 4 | Grinder Endpoint | ⏳ Next | POST /api/grinder/process |
| 5 | Sandbox Service | ✅ Complete | Docker lifecycle + cleanup |
| 6 | Challenge Endpoints | ⏳ Pending | /start, /submit, /skip |
| 7 | Progress Endpoints | ⏳ Pending | Summary, per-course, weak topics |
| 8 | File Watcher | ⏳ Pending | watchdog on ./drop/ |
| 9 | Frontend Scaffold | ⏳ Pending | Vite + React + Tailwind |
| 10 | Home Page | ⏳ Pending | Course grid |
| 11 | Course Page | ⏳ Pending | Topics + challenge list |
| 12 | Challenge Page | ⏳ Pending | Terminal iframe + submit |
| 13 | Stats Page | ⏳ Pending | Progress dashboard |
| 14 | Docker Compose | ⏳ Pending | Wire everything |
| 15 | README | ⏳ Pending | Documentation |

## Issues Discovered & Resolved

### 2026-03-23 — Schema Mismatch (FIXED)
**Problem:** Initial database subagent created generic LMS schema instead of CyberLab spec.
**Resolution:** Fixes subagent corrected all models to use SHA256 string PKs and proper fields.

### 2026-03-23 — Missing sandbox.py (FIXED)
**Problem:** Sandbox subagent reported completion but file was missing.
**Resolution:** Fixes subagent created proper sandbox.py with all required functions.

### 2026-03-23 — Wrong file paths (FIXED)
**Problem:** AI/grinder subagent wrote files to wrong directory.
**Resolution:** Moved files to correct location in cyberlab/backend/services/.

## Session History

### 2026-03-23 — Session 1
- Spawned parallel subagents for Database (Step 1) and Sandbox (Step 5)
- Created project directory structure
- Created plan document

### 2026-03-23 — Session 1 (continued)
- Database subagent completed — but with wrong schema
- Sandbox subagent completed — Docker images exist, but sandbox.py missing
- Spawned AI client + grinder service subagent (wrote to wrong path)
- Spawned fixes subagent to correct schema and create missing files

### 2026-03-23 — Session 1 (verification)
- Moved ai_client.py and grinder.py to correct location
- Wrote and ran test_foundation.py — **ALL TESTS PASSED**
- Verified: SHA256 string PKs, cascade deletes, sandbox imports

## Next Actions
- Build FastAPI main.py with all routers
- Create grinder endpoint (POST /api/grinder/process)
- Build challenge endpoints (/start, /submit, /skip)
- Build progress endpoints
- Create file watcher (watchdog)
- Scaffold frontend (Vite + React + Tailwind)

## Foundation Test Results
```
[1/6] Database imports ✅
[2/6] Table creation ✅
[3/6] Course SHA256 ID ✅
[4/6] Topic SHA256 ID ✅
[5/6] Challenge SHA256 ID ✅ (deterministic)
[6/6] Sandbox imports ✅
```
