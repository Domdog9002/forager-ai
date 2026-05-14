# Rebuild the packaged launcher (PyInstaller one-file exe) with a full scrub of prior outputs.
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_forager_exe.ps1
# Wipe PyInstaller outputs only (no rebuild):
#   powershell -ExecutionPolicy Bypass -File scripts\build_forager_exe.ps1 -CleanOnly
#
# Close Forager_Dev_Suite*.exe before running or the script cannot delete locked binaries.
param(
    [switch]$CleanOnly
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$dist = Join-Path $root "dist"
$buildRoot = Join-Path $root "build"
$buildProj = Join-Path $root "build\Forager_Dev_Suite"

function Test-ForagerExeRunning {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ($_.Path -like "*Forager_Dev_Suite*.exe") }
}

function Remove-ForagerDistArtifacts {
    if (-not (Test-Path $dist)) { return }
    Get-ChildItem -Path $dist -Filter "Forager_Dev_Suite*" -ErrorAction SilentlyContinue |
        Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    # PyInstaller sometimes drops warn/analysis files next to the exe name stem.
    foreach ($pat in @("warn-Forager_Dev_Suite*.txt", "xref-Forager_Dev_Suite*.html")) {
        Get-ChildItem -Path $dist -Filter $pat -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

function Remove-ForagerBuildWork {
    if (Test-Path $buildProj) {
        Remove-Item -Path $buildProj -Recurse -Force -ErrorAction SilentlyContinue
    }
    # Remove stray one-file PKG fragments if PyInstaller used a different work dir name.
    if (Test-Path $buildRoot) {
        Get-ChildItem -Path $buildRoot -Directory -Filter "Forager_Dev_Suite*" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$running = @(Test-ForagerExeRunning)
if ($running.Count -gt 0) {
    Write-Warning "Close Forager_Dev_Suite*.exe (or end task) - $($running.Count) matching process(es) may lock dist files."
    $running | ForEach-Object { Write-Warning "  PID $($_.Id) $($_.Path)" }
}

Write-Host "Cleaning dist + build work dirs (Forager_Dev_Suite*)..."
Remove-ForagerDistArtifacts
Remove-ForagerBuildWork

if ($CleanOnly) {
    Write-Host "CleanOnly: done. No PyInstaller run."
    exit 0
}

py -3 -m PyInstaller "Forager_Dev_Suite.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exes = @(Get-ChildItem -Path $dist -Filter "Forager_Dev_Suite*.exe" -ErrorAction SilentlyContinue)
if ($exes.Count -eq 0) {
    Write-Warning 'Build finished but no Forager_Dev_Suite*.exe found under dist/'
    exit 1
}
foreach ($x in $exes) {
    Write-Host "OK: $($x.FullName)"
}
