#!/usr/bin/env bash
# Full demo: compose stack (optional) + run_demo_flow.py inside API.
#
# One-shot (from repo root, needs Docker):
#   DEMO_COMPOSE_BOOT=1 ./scripts/demo_flow.sh
#
# If API is already up with worker:
#   ./scripts/demo_flow.sh
#
# Env: DEMO_API_BASE (default http://127.0.0.1:8000/api/v1), DEMO_*_TIMEOUT — see run_demo_flow.py
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${DEMO_COMPOSE_BOOT:-}" == "1" ]]; then
	docker compose up -d --build postgres redis api worker
	echo "Waiting for API…"
	for _ in $(seq 1 90); do
		if curl -sf "${DEMO_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}" >/dev/null 2>&1; then
			break
		fi
		sleep 2
	done
fi

exec docker compose exec -T api python scripts/run_demo_flow.py "$@"
