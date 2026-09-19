#!/usr/bin/env bash
# Launches the backend (FastAPI/uvicorn) and frontend (Vite) dev servers together.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "$ROOT_DIR/backend/venv/Scripts/python.exe" ]; then
  PYTHON="$ROOT_DIR/backend/venv/Scripts/python.exe"
else
  PYTHON="$ROOT_DIR/backend/venv/bin/python"
fi

cleanup() {
  echo "Stopping servers..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting backend (FastAPI) on http://localhost:8000 ..."
(cd "$ROOT_DIR/backend" && "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

echo "Starting frontend (Vite) on http://localhost:5174 ..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

wait
