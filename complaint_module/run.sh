#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[*] Setting up virtual environment..."
    ~/.local/bin/uv venv --python /home/aditya/.local/bin/python3.11 .venv
    ~/.local/bin/uv pip install -r requirements.txt --python .venv
fi

echo "[*] Starting Civic Complaint & Escalation Service on http://localhost:8001"
echo "[*] Open UI: http://localhost:8001"
.venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8001 --reload
