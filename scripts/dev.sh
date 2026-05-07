#!/usr/bin/env bash
# backend (uvicorn) + frontend (vite) を 1 コマンドで起動する
# 使い方: ./scripts/dev.sh [--backend-port 8000] [--frontend-port 5173]
# Ctrl+C で両方停止

set -euo pipefail

BACKEND_PORT=8000
FRONTEND_PORT=5173

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port) BACKEND_PORT="$2"; shift 2 ;;
    --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--backend-port N] [--frontend-port N]"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PIDS=()
cleanup() {
  echo
  echo "[dev.sh] stopping..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

echo "[dev.sh] backend  → http://localhost:${BACKEND_PORT}"
echo "[dev.sh] frontend → http://localhost:${FRONTEND_PORT}"
echo

(
  cd backend
  uv run uvicorn src.app.main:app --reload --port "$BACKEND_PORT" 2>&1 | sed 's/^/[backend] /'
) &
PIDS+=($!)

(
  cd frontend
  pnpm dev --port "$FRONTEND_PORT" 2>&1 | sed 's/^/[frontend] /'
) &
PIDS+=($!)

wait
