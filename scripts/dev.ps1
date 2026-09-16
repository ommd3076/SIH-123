# PowerShell launcher for Windows environments
Write-Host "Starting Distributed Predictive Fleet Graph services..." -ForegroundColor Cyan

# Check Python environment
python --version

# Launch Next.js dev server
Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run dev"

# Launch supervisor
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m robotics_ws.supervisor.launch"

Write-Host "Fleet services started. Open http://localhost:3000 to view dashboard." -ForegroundColor Green
