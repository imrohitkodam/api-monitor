#!/bin/bash

# Web App Startup Script
echo "========================================="
echo " Starting API Auditor Web Application"
echo "========================================="

# Get directory of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 1. Install/Verify Python Dependencies
echo "[1/4] Checking python dependencies..."
pip install -r requirements.txt

# 2. Install/Verify Frontend Dependencies
echo "[2/4] Checking frontend dependencies..."
cd frontend
npm install
cd "$DIR"

# 3. Start Flask Backend (in background)
echo "[3/4] Starting Flask backend on port 5000..."
python3 backend/app.py &
BACKEND_PID=$!

# 4. Start React Frontend
echo "[4/4] Starting React frontend on port 5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

# Handle shutdown gracefully
cleanup() {
    echo -e "\nStopping webapp..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep script running
wait
