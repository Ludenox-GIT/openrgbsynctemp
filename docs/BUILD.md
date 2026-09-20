# Building OpenRGB Temp Sync

This document describes the reproducible build and packaging process for the unified one-app product.

## Prerequisites

1. **Python 3.12 (64-bit)**
   - Dependencies: `pillow`, `pystray`, `openrgb-python`, `psutil`, `pywin32`, `pyinstaller`
   - Requirements: `requirements.in`, `requirements-dev.in`, `requirements.lock`
2. **.NET 8 SDK**
   - Required for building the self-contained sensor bridge (`sensor-bridge/OpenRGBTempSync.SensorBridge.csproj`).
3. **Inno Setup 6.7.3+**
   - Required for compiling the single installer package (`installer/OpenRGBTempSync.iss`).
4. **Vendor Binaries**
   - Pinned OpenRGB 1.0 portable zip (`OpenRGB_1.0_Windows_64_81bbe18.zip`).

## Step-by-Step Build Pipeline

### 1. Verify Dependencies & Staging
Verify staged vendor artifacts against the cryptographic lockfile:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-vendor.ps1 -VerifyOnly
```

### 2. Build Sensor Bridge
Publish the self-contained .NET 8 sensor bridge for `win-x64`:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-sensor-bridge.ps1
```

### 3. Build Application Onedir Bundle
Compile the Python application into an elevated onedir package using PyInstaller:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-app.ps1
```

### 4. Build the single-file executable
The final portable EXE embeds the application, OpenRGB, and SensorBridge. It
extracts those payloads to a temporary directory at launch, so no companion
folder is required:
```powershell
pyinstaller OpenRGBTempSync.OneFile.spec --noconfirm --clean
Copy-Item dist/OpenRGBTempSync-Final.exe release/OpenRGBTempSync-Final.exe -Force
```

### 5. Compile Installer
Compile the single Windows installer executable:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-installer.ps1
```

### 6. Verify Release
Run automated release verification checks:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-release.ps1
```

## Release Verification Gates & Unverified States

The build and verification scripts enforce strict verification gates:
- Developer contracts (test discovery across all unit tests and manifest checks) can be verified independently without hardware or compiled payloads.
- Release candidate verification (`scripts/verify-release.ps1`) checks for mandatory release payloads:
  1. OpenRGB payload staged in `vendor/`
  2. SensorBridge compiled executable at `vendor/sensor-bridge/OpenRGBTempSync.SensorBridge.exe`
  3. PyInstaller onedir distribution at `dist/OpenRGBTempSync/OpenRGBTempSync.exe`
  4. Compiled Inno Setup installer at `release/OpenRGBTempSync-Setup-1.0.0.exe`
  5. Required build toolchains (.NET 8 SDK `dotnet`, Inno Setup `iscc`, `pyinstaller`)
- When any mandatory payload or toolchain is absent, the build and verification scripts mark the output as `UNVERIFIED` and do not claim release readiness.
- In automated release workflows, pass `-RequireFullRelease` to `scripts/verify-release.ps1` to fail with an error code if payloads are missing.
- For developer-only contract verification, pass `-DeveloperGateOnly`.
