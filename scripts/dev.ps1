param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created local .env from .env.example. Keep real keys local only."
}

if (-not (Test-Path -LiteralPath ".venv")) {
    python -m venv .venv
}

if (-not $SkipInstall) {
    .\.venv\Scripts\python -m pip install -r requirements.txt
    Push-Location frontend
    npm install
    Pop-Location
}

$Backend = Start-Process powershell -PassThru -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$Root'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend"
)

$Frontend = Start-Process powershell -PassThru -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location '$Root\frontend'; npm run dev"
)

Write-Host "Backend started in process $($Backend.Id): http://127.0.0.1:8000"
Write-Host "Frontend started in process $($Frontend.Id): http://127.0.0.1:5173"
Write-Host "Health check: http://127.0.0.1:8000/api/health"
