#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build WinX.exe (single-file, GUI) with PyInstaller.

.EXAMPLE
    pwsh ./build/build.ps1
    pwsh ./build/build.ps1 -Clean
#>
param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    if (-not (Test-Path '.venv')) {
        Write-Host '[1/4] Creating the virtual environment...' -ForegroundColor Cyan
        python -m venv .venv
    }
    & "$root\.venv\Scripts\Activate.ps1"

    Write-Host '[2/4] Installing dependencies...' -ForegroundColor Cyan
    python -m pip install --upgrade pip | Out-Null
    pip install -r requirements.txt
    pip install 'pyinstaller>=6.3'

    Write-Host '[3/4] Running the self-test...' -ForegroundColor Cyan
    python main.py --selftest
    if ($LASTEXITCODE -ne 0) { throw 'Self-test failed; aborting build.' }

    Write-Host '[4/4] Building with PyInstaller...' -ForegroundColor Cyan
    if ($Clean) {
        Remove-Item -Recurse -Force build/WinX, dist -ErrorAction SilentlyContinue
    }
    pyinstaller build/WinX.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

    $exe = Get-Item dist/WinX.exe
    Write-Host "`nBuilt $($exe.FullName) ($([math]::Round($exe.Length / 1MB, 1)) MB)" -ForegroundColor Green
}
finally {
    Pop-Location
}
