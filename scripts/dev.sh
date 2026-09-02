#!/usr/bin/env bash
# SIH26123 — launch the full live stack:
#   10 robot edge agents + 6 JECs + allocator (Zenoh plane)
#   + telemetry bridge (WebSocket/REST :8010)
#   + Next.js dashboard (:3000)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

echo "[1/3] starting fleet supervisor (10 robots, 6 JECs, allocator)..."
(setsid python3 -m robotics_ws.supervisor --seed 7 > logs/supervisor.log 2>&1 < /dev/null &)
sleep 3

echo "[2/3] starting telemetry bridge on :8010..."
(setsid python3 -m robotics_ws.telemetry_bridge > logs/bridge.log 2>&1 < /dev/null &)
sleep 4

echo "[3/3] starting dashboard (Next.js :3000)..."
(bun run dev > /dev/null 2>&1 &)

sleep 4
curl -s --max-time 5 http://localhost:8010/api/health && echo " <- bridge"
echo
echo "Live view:   http://localhost:3000  (landing -> 'Launch live simulation')"
echo "Stop:        ./scripts/stop.sh"
echo "Experiments: python3 -m robotics_ws.experiment_runner.runner"
