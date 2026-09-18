@echo off
title FleetGraph AI
echo [1/2] Starting lightweight Python bridge...
start cmd /k python -m robotics_ws.telemetry_bridge --lightweight
timeout /t 2 /nobreak >nul
echo [2/2] Starting Next.js Web Dashboard...
start cmd /k npm.cmd run dev
echo Ready at http://localhost:3000
