#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
BACKEND_PORT="${CYBERLAB_BACKEND_PORT:-18080}"

if [[ ! -d "$BACKEND_DIR" ]]; then
	echo "❌ Backend directory not found: $BACKEND_DIR" >&2
	exit 1
fi

if command -v lsof >/dev/null 2>&1; then
	pids="$(lsof -tiTCP:${BACKEND_PORT} -sTCP:LISTEN || true)"
	if [[ -n "$pids" ]]; then
		echo "⚠️ Port ${BACKEND_PORT} in use. Stopping existing process(es): $pids"
		kill $pids || true
		sleep 1

		stale_pids="$(lsof -tiTCP:${BACKEND_PORT} -sTCP:LISTEN || true)"
		if [[ -n "$stale_pids" ]]; then
			echo "⚠️ Force-stopping stubborn process(es): $stale_pids"
			kill -9 $stale_pids || true
		fi
	fi
fi

cd "$BACKEND_DIR"

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
	# shellcheck disable=SC1091
	source "$ROOT_DIR/.venv/bin/activate"
elif [[ -f "$BACKEND_DIR/venv/bin/activate" ]]; then
	# shellcheck disable=SC1091
	source "$BACKEND_DIR/venv/bin/activate"
fi

echo "🚀 Starting backend on http://127.0.0.1:${BACKEND_PORT}"
exec python -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload
