#!/bin/bash
pkill -f "uvicorn" 2>/dev/null
cd /home/swan/Projects/controlPlaneAI
source venv/bin/activate
uvicorn main:app --port 8008 > server.log 2>&1 &
SERVER_PID=$!
sleep 15
sed -i 's/8006/8008/g' test_action_engine.py
python test_action_engine.py
kill $SERVER_PID
