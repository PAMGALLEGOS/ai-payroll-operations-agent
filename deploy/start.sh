#!/usr/bin/env bash
# Container entrypoint for Cloud Run (approved D1, academic PoC).
#
#   1. FastAPI (uvicorn) on 127.0.0.1:${API_PORT} — internal only, never public.
#   2. Waits until GET /health answers.
#   3. Streamlit on 0.0.0.0:${PORT} — the only port Cloud Run exposes.
#
# The UI keeps talking to the API over HTTP (D10). If either process stops, the
# script stops the other and exits non-zero, so Cloud Run restarts the container.
# Logs go to stdout (JSON events from the Agent) -> Cloud Logging.
set -euo pipefail

PORT="${PORT:-8080}"
API_PORT="${API_PORT:-8000}"
export API_BASE_URL="http://127.0.0.1:${API_PORT}"   # the UI always uses the internal API

echo "[start] API on 127.0.0.1:${API_PORT} (internal) · UI on 0.0.0.0:${PORT} (public)"
echo "[start] providers: LLM_PROVIDER=${LLM_PROVIDER:-gemini} EMBEDDINGS_PROVIDER=${EMBEDDINGS_PROVIDER:-gemini}"

python -m uvicorn app.api.main:app --host 127.0.0.1 --port "${API_PORT}" --no-access-log &
API_PID=$!

stop_all() {
  kill -TERM "${API_PID}" "${UI_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap 'stop_all; exit 0' TERM INT

# Wait for the API (max 60 s). /health answers 200 while the process is alive.
python - <<PY
import sys, time, httpx
deadline = time.time() + 60
while time.time() < deadline:
    try:
        status = httpx.get("${API_BASE_URL}/health", timeout=2).json()
        print(f"[start] API health: {status['status']}", flush=True)
        sys.exit(0)
    except Exception:
        time.sleep(0.5)
print("[start] API did not answer /health within 60 s", flush=True)
sys.exit(1)
PY

python -m streamlit run app/web/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port "${PORT}" \
  --server.headless true \
  --browser.gatherUsageStats false &
UI_PID=$!

# Exit as soon as either process ends (Cloud Run then restarts the container).
set +e
wait -n "${API_PID}" "${UI_PID}"
CODE=$?
echo "[start] a process stopped (exit ${CODE}); stopping the container"
stop_all
exit $(( CODE == 0 ? 1 : CODE ))
