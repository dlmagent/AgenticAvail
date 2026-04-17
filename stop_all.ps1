# stop_all.ps1
$ErrorActionPreference = "SilentlyContinue"

$ports = @(3000, 8000)


$stopped = @()

foreach ($p in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue

    if ($connections) {
        foreach ($c in $connections) {
            try {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
                $stopped += $p
            } catch {}
        }
    }
}

if ($stopped.Count -gt 0) {
    $uniquePorts = $stopped | Sort-Object -Unique
    Write-Host "Stopped services on ports: $($uniquePorts -join ', ')." -ForegroundColor Green
} else {
    Write-Host "No running services found on expected ports." -ForegroundColor Yellow
}
