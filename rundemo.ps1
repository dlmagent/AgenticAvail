# Run from repo root in VS Code PowerShell:
#   .\rundemo.ps1
#
# Assumes these commands work:
#   pip
#   uvicorn
#   npm

$ErrorActionPreference = "Stop"

$envFile = Join-Path (Get-Location).Path ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) { return }
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if ($value.Length -ge 2) {
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
    }
    if ($name) {
      Set-Item -Path "Env:$name" -Value $value
    }
  }
}

$env:OPENAI_MODEL = if ($env:OPENAI_MODEL) { $env:OPENAI_MODEL } else { "gpt-4.1" }
$env:VITE_BACKEND_PROXY_TARGET = "http://127.0.0.1:8000"

$backendPort = 8000
$frontendPort = 3000

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found on PATH: $name"
  }
}

function Stop-Port($port) {
  $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  foreach ($connection in $connections) {
    try { Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Start-Uvicorn($serviceName, $workDir, $port, $outLog, $errLog) {
  if (Test-Path $outLog) { Remove-Item $outLog -Force | Out-Null }
  if (Test-Path $errLog) { Remove-Item $errLog -Force | Out-Null }

  Write-Host "Starting $serviceName (port $port) ..." -ForegroundColor Cyan

  $args = @("app:app", "--host", "127.0.0.1", "--port", $port, "--log-level", "info")

  return Start-Process -FilePath "uvicorn" `
    -ArgumentList $args `
    -WorkingDirectory $workDir `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -NoNewWindow `
    -PassThru
}

function Wait-Healthy($url, $name, $timeoutSeconds = 25) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        Write-Host "$name healthy: $url" -ForegroundColor Green
        return
      }
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  throw "$name did not become healthy in $timeoutSeconds seconds: $url"
}

Assert-Command "pip"
Assert-Command "uvicorn"
Assert-Command "npm.cmd"

if (-not $env:OPENAI_API_KEY) {
  throw "OPENAI_API_KEY is not set. Set it in your shell before running .\rundemo.ps1."
}

Write-Host "`n=== Installing dependencies ===" -ForegroundColor Yellow
$constraints = ".\constraints.txt"
pip install -r ".\backend\requirements.txt" -c $constraints
Push-Location ".\frontend"
try {
  npm.cmd install
} finally {
  Pop-Location
}

Write-Host "`n=== Freeing ports if already used ===" -ForegroundColor Yellow
Stop-Port $backendPort
Stop-Port $frontendPort

$root = (Get-Location).Path
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$backendOut = Join-Path $logDir "backend.out.log"
$backendErr = Join-Path $logDir "backend.err.log"
$frontendOut = Join-Path $logDir "frontend.out.log"
$frontendErr = Join-Path $logDir "frontend.err.log"

Write-Host "`n=== Starting services ===" -ForegroundColor Yellow
$backendProc = Start-Uvicorn "Unified Backend" (Join-Path $root "backend") $backendPort $backendOut $backendErr

if (Test-Path $frontendOut) { Remove-Item $frontendOut -Force | Out-Null }
if (Test-Path $frontendErr) { Remove-Item $frontendErr -Force | Out-Null }
Write-Host "Starting React frontend (port $frontendPort) ..." -ForegroundColor Cyan
$frontendProc = Start-Process -FilePath "npm.cmd" `
  -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$frontendPort") `
  -WorkingDirectory (Join-Path $root "frontend") `
  -RedirectStandardOutput $frontendOut `
  -RedirectStandardError $frontendErr `
  -NoNewWindow `
  -PassThru

Write-Host "`n=== Waiting for health checks ===" -ForegroundColor Yellow
Wait-Healthy "http://127.0.0.1:8000/health" "Unified Backend"
Wait-Healthy "http://127.0.0.1:3000" "React Frontend"

Write-Host "`nAll services are up." -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:3000"
Write-Host "Backend:  http://127.0.0.1:8000"
Start-Process "http://127.0.0.1:3000" | Out-Null

Write-Host "`nLogs are here: .\logs\" -ForegroundColor Yellow
Write-Host "Tail logs with:" -ForegroundColor Yellow
Write-Host "  Get-Content .\logs\backend.out.log -Wait"
Write-Host "  Get-Content .\logs\backend.err.log -Wait"
Write-Host "  Get-Content .\logs\frontend.out.log -Wait"
Write-Host "  Get-Content .\logs\frontend.err.log -Wait"
Write-Host ""
Write-Host "Stop services with: .\stop_all.ps1" -ForegroundColor Yellow
