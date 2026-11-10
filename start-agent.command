#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先按 README 的快速开始安装 .venv 和依赖。'
  exit 1
fi
if curl -fsS http://127.0.0.1:8860/api/health >/dev/null 2>&1; then
  open http://127.0.0.1:8860/
  exit 0
fi
.venv/bin/python run_agent.py --port 8860 &
LINKDESK_SERVER_PID=$!
trap 'kill "$LINKDESK_SERVER_PID" 2>/dev/null || true' EXIT
for attempt in {1..40}; do
  if curl -fsS http://127.0.0.1:8860/api/health >/dev/null 2>&1; then
    open http://127.0.0.1:8860/
    wait "$LINKDESK_SERVER_PID"
    exit 0
  fi
  kill -0 "$LINKDESK_SERVER_PID" 2>/dev/null || exit 1
  sleep 0.5
done
echo '启动超时，请查看上方错误信息。'
exit 1
