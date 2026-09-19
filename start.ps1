# Launches the backend (FastAPI/uvicorn) and frontend (Vite) dev servers together.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$backend = Start-Process -PassThru -NoNewWindow `
  -FilePath "$root\backend\venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory "$root\backend"

$frontend = Start-Process -PassThru -NoNewWindow `
  -FilePath "npm" -ArgumentList "run", "dev" `
  -WorkingDirectory "$root\frontend"

Write-Host "Backend PID: $($backend.Id)  |  Frontend PID: $($frontend.Id)"
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5174"
Write-Host "Press Ctrl+C to stop both."

try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
  Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue
}
