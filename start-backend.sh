#!/bin/bash
cd /root/cyberlab/backend
source venv/bin/activate
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080
