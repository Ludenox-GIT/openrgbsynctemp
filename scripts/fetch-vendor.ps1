<#
.SYNOPSIS
    Acquires and verifies vendor dependencies based on third_party/dependencies.lock.json.
.PARAMETER VerifyOnly
    Checks hashes of staged files in vendor/ without downloading (read-only default mode).
.PARAMETER AcquireOpenRgb
    Acquires the pinned OpenRGB release artifact, verifies its SHA-256 hash, extracts, and normalizes it to vendor/OpenRGB.
#>
param (
    [switch]$VerifyOnly,
    [switch]$AcquireOpenRgb
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\.."
$ManifestPath = Join-Path $RepoRoot 'third_party\dependencies.lock.json'
$VendorDir = Join-Path $RepoRoot 'vendor'

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Error "Manifest not found at $ManifestPath"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not (Test-Path -LiteralPath $VendorDir)) {
    New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null
}

$openrgbArtifact = $manifest.artifacts | Where-Object { $_.name -eq 'openrgb' }
if (-not $openrgbArtifact) {
    Write-Error "Artifact 'openrgb' not defined in manifest."
}

if ($AcquireOpenRgb) {
    Write-Host "Acquiring and normalizing OpenRGB release artifact..."
    $filename = $openrgbArtifact.filename
    $expectedHash = $openrgbArtifact.sha256.ToLower()
    $targetZip = Join-Path $VendorDir $filename
    $openrgbDir = Join-Path $VendorDir 'OpenRGB'
    $finalExe = Join-Path $openrgbDir 'OpenRGB.exe'

    if (-not (Test-Path -LiteralPath $targetZip)) {
        Write-Host "Downloading $filename from $($openrgbArtifact.source_url)..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        try {
            Invoke-WebRequest -Uri $openrgbArtifact.source_url -OutFile $targetZip -UseBasicParsing
        } catch {
            if (Test-Path -LiteralPath $targetZip) {
                Remove-Item -LiteralPath $targetZip -Force -ErrorAction SilentlyContinue
            }
            Write-Error "Failed to download OpenRGB: $_"
        }
    }

    # Verify SHA-256: never silently accept a wrong hash
    $actualHash = (Get-FileHash -LiteralPath $targetZip -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedHash) {
        Remove-Item -LiteralPath $targetZip -Force -ErrorAction SilentlyContinue
        Write-Error "SHA-256 hash mismatch for $filename. Expected $expectedHash, got $actualHash. Staged file removed."
    }
    Write-Host "[OK] $filename SHA-256 verified: $actualHash" -ForegroundColor Green

    # Extract and normalize
    $stageDir = Join-Path $VendorDir '_openrgb_extract_stage'
    if (Test-Path -LiteralPath $stageDir) {
        Remove-Item -LiteralPath $stageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    try {
        Write-Host "Extracting archive to staging directory..."
        Expand-Archive -LiteralPath $targetZip -DestinationPath $stageDir -Force

        $foundExe = Get-ChildItem -LiteralPath $stageDir -Recurse -Filter "OpenRGB.exe" | Select-Object -First 1
        if (-not $foundExe) {
            Write-Error "Archive extraction did not yield OpenRGB.exe"
        }

        $sourceDir = $foundExe.DirectoryName
        Write-Host "Normalizing OpenRGB from '$sourceDir' to '$openrgbDir'..."

        if (-not (Test-Path -LiteralPath $openrgbDir)) {
            New-Item -ItemType Directory -Path $openrgbDir -Force | Out-Null
        }

        Get-ChildItem -LiteralPath $sourceDir | ForEach-Object {
            $destPath = Join-Path $openrgbDir $_.Name
            if (Test-Path -LiteralPath $destPath) {
                Remove-Item -LiteralPath $destPath -Recurse -Force
            }
            Move-Item -LiteralPath $_.FullName -Destination $destPath -Force
        }

        # Remove leftover nested folder if present
        $nestedFolder = Join-Path $openrgbDir 'OpenRGB Windows 64-bit'
        if (Test-Path -LiteralPath $nestedFolder) {
            Remove-Item -LiteralPath $nestedFolder -Recurse -Force
        }

        if (-not (Test-Path -LiteralPath $finalExe)) {
            Write-Error "OpenRGB.exe missing after normalization at $finalExe"
        }
        Write-Host "[OK] OpenRGB normalized at $finalExe with companion DLL and bin files." -ForegroundColor Green
    } finally {
        if (Test-Path -LiteralPath $stageDir) {
            Remove-Item -LiteralPath $stageDir -Recurse -Force
        }
    }
}

Write-Host "Verifying staged vendor artifacts..."
$allPassed = $true

foreach ($artifact in $manifest.artifacts) {
    $filename = $artifact.filename
    if (-not $filename) { continue }
    $targetPath = Join-Path $VendorDir $filename
    $expectedHash = $artifact.sha256

    if (Test-Path -LiteralPath $targetPath) {
        $actualHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLower()
        if ($expectedHash -match '^[a-fA-F0-9]{64}$') {
            if ($actualHash -eq $expectedHash.ToLower()) {
                Write-Host "[OK] $filename ($actualHash)" -ForegroundColor Green
            } else {
                Write-Host "[MISMATCH] $filename expected $expectedHash, got $actualHash" -ForegroundColor Red
                $allPassed = $false
            }
        } else {
            Write-Host "[GATED] $filename staged with gated hash rule ($expectedHash)" -ForegroundColor Yellow
        }
    } else {
        if ($VerifyOnly -or (-not $AcquireOpenRgb)) {
            Write-Host "[MISSING] $filename (not staged)" -ForegroundColor Gray
        } else {
            Write-Host "[SKIP-DOWNLOAD] ${filename}: automatic external downloading disabled by repo policy." -ForegroundColor Yellow
        }
    }
}

if (-not $allPassed) {
    exit 1
}
Write-Host "Vendor verification pass complete."
exit 0
