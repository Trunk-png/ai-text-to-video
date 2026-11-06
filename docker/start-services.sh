#!/usr/bin/env bash
set -euo pipefail
cd "${COMFY_HOME:-/opt/ComfyUI}"

cleanup() {
  kill "${COMFYUI_PID:-}" "${WORKER_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

python main.py --listen "${COMFY_LISTEN:-127.0.0.1}" --port "${PORT:-8188}" \
  --disable-metadata --preview-method none --force-channels-last &
COMFYUI_PID=$!

for _ in $(seq 1 120); do
  curl -fs "http://127.0.0.1:${PORT:-8188}/system_stats" >/dev/null && break
  kill -0 "$COMFYUI_PID" 2>/dev/null || exit 1
  sleep 2
done
curl -fs "http://127.0.0.1:${PORT:-8188}/system_stats" >/dev/null

python worker.py &
WORKER_PID=$!
while kill -0 "$COMFYUI_PID" 2>/dev/null && kill -0 "$WORKER_PID" 2>/dev/null; do
  touch /tmp/worker_heartbeat
  sleep 15
done
exit 1

