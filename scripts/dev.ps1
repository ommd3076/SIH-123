# PowerShell dev launcher for Windows
param (
    [switch]$Distributed = $false
)

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host " FleetGraph AI — Distributed AMR Fleet Grid     " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

$workDir = (Get-Location).Path

# 1. Start Python Fleet Backend
if ($Distributed) {
    Write-Host "[1/2] Starting 20-process distributed fleet (supervisor)..." -ForegroundColor Yellow
    Start-Process powershell -WorkingDirectory $workDir -ArgumentList "-NoExit", "-Command", "python -m robotics_ws.supervisor --seed 7"
    Start-Sleep -Seconds 2
    Start-Process powershell -WorkingDirectory $workDir -ArgumentList "-NoExit", "-Command", "python -m robotics_ws.telemetry_bridge"
} else {
    Write-Host "[1/2] Starting lightweight single-process fleet engine (super fast & light)..." -ForegroundColor Green
    Start-Process powershell -WorkingDirectory $workDir -ArgumentList "-NoExit", "-Command", "python -m robotics_ws.telemetry_bridge --lightweight"
}

# 2. Start Next.js Frontend
Write-Host "[2/2] Starting Next.js dashboard (:3000)..." -ForegroundColor Green
Start-Process powershell -WorkingDirectory $workDir -ArgumentList "-NoExit", "-Command", "npm.cmd run dev"

Start-Sleep -Seconds 3
Write-Host "`nReady! Dashboard running at: http://localhost:3000" -ForegroundColor Cyan
Write-Host "To run full multi-process mode next time: .\scripts\dev.ps1 -Distributed" -ForegroundColor Gray