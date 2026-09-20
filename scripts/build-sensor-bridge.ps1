<#
.SYNOPSIS
    Compiles and publishes the self-contained .NET 8 sensor bridge.
#>
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\.."
$ProjectFile = Join-Path $RepoRoot 'sensor-bridge\OpenRGBTempSync.SensorBridge.csproj'
$OutputDir = Join-Path $RepoRoot 'vendor\sensor-bridge'

$dotnetCmd = Get-Command dotnet -ErrorAction SilentlyContinue

if (-not $dotnetCmd) {
    Write-Warning "[GATE] .NET SDK ('dotnet') is not found on PATH. Sensor bridge build marked UNVERIFIED."
    exit 0
}

Write-Host "Publishing self-contained sensor bridge for win-x64..."
dotnet publish $ProjectFile -c Release -r win-x64 --self-contained true -o $OutputDir --source https://api.nuget.org/v3/index.json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to publish sensor bridge."
}

Write-Host "Sensor bridge published to $OutputDir"
