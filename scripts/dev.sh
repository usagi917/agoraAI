#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "${backend_pid}" ]]; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${frontend_pid}" ]]; then
    kill "${frontend_pid}" 2>/dev/null || true
  fi
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

if [[ ! -f "${ROOT_DIR}/.env" && -f "${ROOT_DIR}/.env.example" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "Created .env from .env.example"
fi

if [[ ! -d "${ROOT_DIR}/backend/.venv" ]]; then
  echo "Installing backend dependencies..."
  (cd "${ROOT_DIR}/backend" && uv sync --extra dev)
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  (cd "${ROOT_DIR}/frontend" && pnpm install)
fi

echo "Starting backend on http://localhost:${BACKEND_PORT}"
(cd "${ROOT_DIR}/backend" && uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT}") &
backend_pid="$!"

echo "Starting frontend on http://localhost:${FRONTEND_PORT}"
(cd "${ROOT_DIR}/frontend" && pnpm dev --host 0.0.0.0 --port "${FRONTEND_PORT}") &
frontend_pid="$!"

echo "Press Ctrl+C to stop both servers."
while true; do
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    echo "Backend stopped."
    exit 1
  fi

  if ! kill -0 "${frontend_pid}" 2>/dev/null; then
    echo "Frontend stopped."
    exit 1
  fi

  sleep 1
done
