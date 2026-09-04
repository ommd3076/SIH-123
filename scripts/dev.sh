#!/usr/bin/env bash
# SIH26123 runtime profiles:
#   --demo      : fleet + bridge + dashboard
#   --headless  : fleet + bridge (no browser UI)
#   --visual    : alias of --demo (kept for ROS/Gazebo migration parity)
#   --benchmark : experiment runner only (no bridge, no dashboard)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

MODE="${1:---demo}"

start_fleet() {
  echo "[1/3] starting fleet supervisor (10 robots, JECs, allocator)..."
  (setsid python3 -m robotics_ws.supervisor --seed 7 > logs/supervisor.log 2>&1 < /dev/null &)
  sleep 3
}

start_bridge() {
  echo "[2/3] starting telemetry bridge on :8010..."
  (setsid python3 -m robotics_ws.telemetry_bridge > logs/bridge.log 2>&1 < /dev/null &)
  sleep 4
  curl -s --max-time 5 http://localhost:8010/api/health && echo " <- bridge"
}

start_dashboard() {
  echo "[3/3] starting dashboard (Next.js :3000)..."
  (bun run dev > /dev/null 2>&1 &)
  sleep 4
  echo "Live view:   http://localhost:3000  (landing -> 'Launch live simulation')"
}

case "$MODE" in
  --demo)
    start_fleet
    start_bridge
    start_dashboard
    ;;
  --headless)
    start_fleet
    start_bridge
    echo "[3/3] headless profile active (dashboard not launched)."
    ;;
  --visual)
    echo "[mode] --visual currently maps to --demo in this non-Gazebo runtime."
    start_fleet
    start_bridge
    start_dashboard
    ;;
  --benchmark)
    echo "[benchmark] running headless experiment suite (no UI)..."
    python3 -m robotics_ws.experiment_runner.runner
    exit 0
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: ./scripts/dev.sh [--demo|--headless|--visual|--benchmark]"
    exit 1
    ;;
esac

echo
echo "Stop:        ./scripts/stop.sh"
echo "Experiments: python3 -m robotics_ws.experiment_runner.runner"
