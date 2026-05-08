#!/usr/bin/env bash
# backend (uvicorn) + frontend (vite) を 1 コマンドで起動する
# 使い方: ./scripts/dev.sh [--backend-port 8000] [--frontend-port 5173]
# Ctrl+C で両方停止

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      BACKEND_PORT="$2"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--backend-port N] [--frontend-port N]"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

PIDS=()

cleanup() {
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    echo
    echo "[dev.sh] stopping..."
    for pid in "${PIDS[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
  fi
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

if [[ ! -f "${ROOT_DIR}/.env" && -f "${ROOT_DIR}/.env.example" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "[dev.sh] created .env from .env.example"
fi

if [[ ! -d "${ROOT_DIR}/backend/.venv" ]]; then
  echo "[dev.sh] installing backend dependencies..."
  (cd "${ROOT_DIR}/backend" && uv sync --extra dev)
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "[dev.sh] installing frontend dependencies..."
  (cd "${ROOT_DIR}/frontend" && pnpm install)
fi

echo "[dev.sh] backend  -> http://localhost:${BACKEND_PORT}"
echo "[dev.sh] frontend -> http://localhost:${FRONTEND_PORT}"
echo

(
  cd "${ROOT_DIR}/backend"
  uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT}" 2>&1 | sed 's/^/[backend] /'
) &
PIDS+=("$!")

(
  cd "${ROOT_DIR}/frontend"
  pnpm dev --host 0.0.0.0 --port "${FRONTEND_PORT}" 2>&1 | sed 's/^/[frontend] /'
) &
PIDS+=("$!")

wait
