<#
.SYNOPSIS
    Builds onedir distribution package using PyInstaller and stages assets.
#>
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\.."

& python -c "import sys, importlib.util; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[GATE] PyInstaller package not installed in current Python environment. Application packaging marked UNVERIFIED."
    exit 0
}

Write-Host "Running PyInstaller onedir build..."
Set-Location $RepoRoot
pyinstaller OpenRGBTempSync.spec --noconfirm --clean

$DistAppDir = Join-Path $RepoRoot 'dist\OpenRGBTempSync'
if (Test-Path $DistAppDir) {
    Write-Host "Staging licenses and third-party notices..."
    $LicenseDir = Join-Path $DistAppDir 'licenses'
    New-Item -ItemType Directory -Force -Path $LicenseDir | Out-Null
    Copy-Item (Join-Path $RepoRoot 'third_party\THIRD-PARTY-NOTICES.md') -Destination $LicenseDir -Force

    $VendorStaged = Join-Path $RepoRoot 'vendor'
    if (Test-Path $VendorStaged) {
        Write-Host "Staging vendor dependencies..."
        Copy-Item -Path $VendorStaged -Destination $DistAppDir -Recurse -Force
    }

    # Check for mandatory release payloads
    $openrgbTarget = Join-Path $DistAppDir 'vendor\OpenRGB\OpenRGB.exe'
    $openrgbTargetFlat = Join-Path $DistAppDir 'OpenRGB.exe'
    $sensorTarget = Join-Path $DistAppDir 'vendor\sensor-bridge\OpenRGBTempSync.SensorBridge.exe'
    $sensorTargetFlat = Join-Path $DistAppDir 'OpenRGBTempSync.SensorBridge.exe'

    $hasOpenRgb = (Test-Path $openrgbTarget) -or (Test-Path $openrgbTargetFlat)
    $hasSensor = (Test-Path $sensorTarget) -or (Test-Path $sensorTargetFlat)

    if (-not $hasOpenRgb -or -not $hasSensor) {
        Write-Warning "[GATE] Mandatory payloads missing in application bundle (OpenRGB: $hasOpenRgb, SensorBridge: $hasSensor). Packaging marked UNVERIFIED (partial build)."
    } else {
        Write-Host "[OK] Application build ready at $DistAppDir with all mandatory payloads."
    }
}
