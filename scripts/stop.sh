#!/usr/bin/env bash
# Stop the live fleet stack (dashboard keeps running under its supervisor).
pkill -f "robotics_ws.supervisor" 2>/dev/null || true
pkill -f "robotics_ws.telemetry_bridge" 2>/dev/null || true
pkill -f "robotics_ws.robot_agent" 2>/dev/null || true
pkill -f "robotics_ws.junction_edge_cell" 2>/dev/null || true
pkill -f "robotics_ws.task_allocator" 2>/dev/null || true
echo "fleet stopped"
