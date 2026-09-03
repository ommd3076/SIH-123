#!/usr/bin/env bash
# SIH26123 — Distributed Predictive Fleet Graph: environment setup
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== [1/3] Python backend dependencies =="
python3 -m pip install --quiet eclipse-zenoh python-socketio aiohttp numpy pytest || {
  echo "pip install failed — if this is a managed environment, use:" >&2
  echo "  python3 -m pip install --break-system-packages eclipse-zenoh python-socketio aiohttp numpy pytest" >&2
  exit 1
}

echo "== [2/3] Frontend dependencies =="
if command -v bun >/dev/null 2>&1; then
  bun install
elif command -v npm >/dev/null 2>&1; then
  npm install
else
  echo "bun/npm not found — install Node.js 20+ and bun" >&2
  exit 1
fi

echo "== [3/3] Smoke tests =="
python3 -m pytest robotics_ws/tests/test_core.py -q

echo
echo "Setup complete. Launch with: ./scripts/dev.sh"
