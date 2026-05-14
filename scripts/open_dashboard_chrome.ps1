# Opens Forager Streamlit in Google Chrome for local UI work (e.g. Cursor Design Mode).
# Starts Streamlit on port 8501 only if nothing is already listening there.
$ErrorActionPreference = "Stop"
$port = 8501
$wd = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $wd "dashboard.py"))) {
    $wd = "c:\Apps\Forager ai"
}
$url = "http://127.0.0.1:$port/"

$busy = $false
try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $busy = $null -ne $conns -and $conns.Count -gt 0
} catch {
    $busy = $false
}

if (-not $busy) {
    Write-Host "Starting Streamlit on port $port..."
    Start-Process -FilePath "py" -ArgumentList @(
        "-3", "-m", "streamlit", "run", "dashboard.py",
        "--server.port", "$port",
        "--server.headless", "true"
    ) -WorkingDirectory $wd -WindowStyle Hidden
    Start-Sleep -Seconds 10
} else {
    Write-Host "Port $port already in use - opening browser only."
}

$candidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LocalAppData "Google\Chrome\Application\chrome.exe")
)
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($chrome) {
    Write-Host "Opening Chrome: $url"
    Start-Process -FilePath $chrome -ArgumentList $url
} else {
    Write-Host "Chrome not found - opening default browser at $url"
    Start-Process $url
}
