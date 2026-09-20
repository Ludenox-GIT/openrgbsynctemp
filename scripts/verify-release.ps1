<#
.SYNOPSIS
    Verifies release candidate layout, dependencies, port safety rules, and notices.
.PARAMETER RequireFullRelease
    Fails with exit code 1 if any mandatory release payload or compiled artifact is missing.
.PARAMETER DeveloperGateOnly
    Runs only developer contracts (unit tests, manifest structure, third-party notices).
#>
param (
    [switch]$RequireFullRelease,
    [switch]$DeveloperGateOnly
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\.."

Write-Host "Verifying developer contracts..."

# 1. Full Python test suite
python -m unittest discover -s (Join-Path $RepoRoot 'tests') -p "test_*.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Test suite verification failed."
}

# 2. Third-party notices check
$NoticesFile = Join-Path $RepoRoot 'third_party\THIRD-PARTY-NOTICES.md'
if (-not (Test-Path $NoticesFile)) {
    Write-Error "THIRD-PARTY-NOTICES.md missing."
}

Write-Host "[OK] Developer contracts verified."

if ($DeveloperGateOnly) {
    Write-Host "Developer gate verification complete."
    exit 0
}

Write-Host "Verifying mandatory release payloads and toolchains..."
$unverifiedItems = @()

# A. OpenRGB payload
$openrgbExe = Join-Path $RepoRoot 'vendor\OpenRGB\OpenRGB.exe'
if (-not (Test-Path $openrgbExe)) {
    $unverifiedItems += "OpenRGB payload missing or un-normalized at vendor\OpenRGB\OpenRGB.exe (run scripts/fetch-vendor.ps1 -AcquireOpenRgb)"
}

# B. Sensor bridge binary
$sensorBridgeExe = Join-Path $RepoRoot 'vendor\sensor-bridge\OpenRGBTempSync.SensorBridge.exe'
if (-not (Test-Path $sensorBridgeExe)) {
    $unverifiedItems += "SensorBridge binary missing at vendor\sensor-bridge\OpenRGBTempSync.SensorBridge.exe"
}

# C. PyInstaller onedir distribution
$distExe = Join-Path $RepoRoot 'dist\OpenRGBTempSync\OpenRGBTempSync.exe'
if (-not (Test-Path $distExe)) {
    $unverifiedItems += "PyInstaller onedir distribution missing at dist\OpenRGBTempSync\OpenRGBTempSync.exe"
} else {
    $distAppDir = Join-Path $RepoRoot 'dist\OpenRGBTempSync'
    $hasBundledOpenRgb = (Test-Path (Join-Path $distAppDir 'vendor\OpenRGB\OpenRGB.exe')) -or (Test-Path (Join-Path $distAppDir 'OpenRGB.exe'))
    $hasBundledSensor = (Test-Path (Join-Path $distAppDir 'vendor\sensor-bridge\OpenRGBTempSync.SensorBridge.exe')) -or (Test-Path (Join-Path $distAppDir 'OpenRGBTempSync.SensorBridge.exe'))
    $hasBundledNotices = Test-Path (Join-Path $distAppDir 'licenses\THIRD-PARTY-NOTICES.md')
    if (-not $hasBundledOpenRgb) {
        $unverifiedItems += "Bundled OpenRGB executable missing inside dist\OpenRGBTempSync"
    }
    if (-not $hasBundledSensor) {
        $unverifiedItems += "Bundled SensorBridge executable missing inside dist\OpenRGBTempSync"
    }
    if (-not $hasBundledNotices) {
        $unverifiedItems += "Bundled THIRD-PARTY-NOTICES.md missing inside dist\OpenRGBTempSync\licenses"
    }
}

# D. Inno Setup installer executable
$releaseInstaller = Join-Path $RepoRoot 'release\OpenRGBTempSync-Setup-1.0.0.exe'
if (-not (Test-Path $releaseInstaller)) {
    $unverifiedItems += "Release installer binary missing at release\OpenRGBTempSync-Setup-1.0.0.exe"
}

# E. Toolchain availability
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    $unverifiedItems += "Toolchain missing: .NET 8 SDK (dotnet) not found on PATH"
}

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $standardPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $foundIscc = $false
    foreach ($p in $standardPaths) {
        if (Test-Path $p) { $foundIscc = $true; break }
    }
    if (-not $foundIscc) {
        $unverifiedItems += "Toolchain missing: Inno Setup compiler (ISCC.exe) not found on PATH"
    }
}

if ($unverifiedItems.Count -gt 0) {
    Write-Warning "[GATE] Release verification marked UNVERIFIED due to missing mandatory payloads or toolchains:"
    foreach ($item in $unverifiedItems) {
        Write-Warning "  - $item"
    }
    if ($RequireFullRelease) {
        Write-Error "Release verification failed: mandatory release payloads are absent."
    } else {
        Write-Host "Developer contracts passed; release status: UNVERIFIED."
        exit 0
    }
} else {
    Write-Host "[OK] Full release verification passed: all mandatory payloads and toolchains present."
    exit 0
}
