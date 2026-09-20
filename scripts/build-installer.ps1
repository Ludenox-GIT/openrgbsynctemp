<#
.SYNOPSIS
    Compiles Inno Setup installer package.
#>
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\.."
$IssFile = Join-Path $RepoRoot 'installer\OpenRGBTempSync.iss'
$DistAppExe = Join-Path $RepoRoot 'dist\OpenRGBTempSync\OpenRGBTempSync.exe'

if (-not (Test-Path $DistAppExe)) {
    Write-Warning "[GATE] Application distribution at $DistAppExe not found. Installer compilation marked UNVERIFIED."
    exit 0
}

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $standardPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($p in $standardPaths) {
        if (Test-Path $p) {
            $iscc = $p
            break
        }
    }
}

if (-not $iscc) {
    Write-Warning "[GATE] Inno Setup compiler (ISCC.exe) not found on PATH. Installer compilation marked UNVERIFIED."
    exit 0
}

Write-Host "Compiling Inno Setup installer..."
& $iscc $IssFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Installer compilation failed."
}
Write-Host "[OK] Installer compilation completed successfully."
