# Start Streamlit (headless) and open Google Chrome for local UI/design work.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$port = 8501

function Test-PortListen([int]$p) {
    try {
        $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
        return [bool]$c
    } catch {
        return $false
    }
}

if (-not (Test-PortListen $port)) {
    Write-Host "Starting Streamlit on port $port ..."
    Start-Process -FilePath py -ArgumentList @(
        "-3", "-m", "streamlit", "run", "dashboard.py",
        "--server.headless", "true",
        "--server.port=$port"
    ) -WorkingDirectory (Get-Location).Path -WindowStyle Normal

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 400
        if (Test-PortListen $port) { break }
    }
    if (-not (Test-PortListen $port)) {
        Write-Error "Streamlit did not start listening on port $port within 90s."
        exit 1
    }
} else {
    Write-Host "Port $port already listening; opening Chrome only."
}

$url = "http://127.0.0.1:$port/"
$chrome = Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
if (-not (Test-Path -LiteralPath $chrome)) {
    $chrome = Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path -LiteralPath $chrome)) {
    $chrome = Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"
}
if (Test-Path -LiteralPath $chrome) {
    Write-Host "Opening Chrome: $url"
    Start-Process -FilePath $chrome -ArgumentList @($url)
} else {
    Write-Warning "Chrome not found. Open in Chrome manually: $url"
    exit 2
}
