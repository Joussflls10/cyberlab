#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
FRONTEND_PORT="${CYBERLAB_FRONTEND_PORT:-5173}"
BACKEND_PORT="${CYBERLAB_BACKEND_PORT:-18080}"
BACKEND_URL="${CYBERLAB_BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

if [[ ! -d "$FRONTEND_DIR" ]]; then
	echo "❌ Frontend directory not found: $FRONTEND_DIR" >&2
	exit 1
fi

if command -v lsof >/dev/null 2>&1; then
	pids="$(lsof -tiTCP:${FRONTEND_PORT} -sTCP:LISTEN || true)"
	if [[ -n "$pids" ]]; then
		echo "⚠️ Port ${FRONTEND_PORT} in use. Stopping existing process(es): $pids"
		kill $pids || true
		sleep 1

		stale_pids="$(lsof -tiTCP:${FRONTEND_PORT} -sTCP:LISTEN || true)"
		if [[ -n "$stale_pids" ]]; then
			echo "⚠️ Force-stopping stubborn process(es): $stale_pids"
			kill -9 $stale_pids || true
		fi
	fi
fi

cd "$FRONTEND_DIR"

echo "🚀 Starting frontend on http://127.0.0.1:${FRONTEND_PORT} (proxy -> ${BACKEND_URL})"
VITE_DEV_PORT="$FRONTEND_PORT" VITE_BACKEND_URL="$BACKEND_URL" \
	exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
