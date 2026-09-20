# Unified RGB Desktop App Baseline Report

- **Date**: 19-09-26
- **RFC**: RFC-001 Baseline, Dependency Manifest, and Redistribution Gate
- **Status**: VERIFIED_BASELINE (with documented offline/hardware gates)

## 1. System and Process Baseline

- **Operating System**: Windows 11 x64
- **CPU**: AMD Ryzen 7 5800X (8 cores / 16 threads)
- **GPU**: NVIDIA GeForce RTX 3060 (12GB)
- **Motherboard / Platform**: MSI MAG B550 TOMAHAWK (MS-7C91)
- **Active RGB/Sensor Processes**:
  - OpenRGB: None currently running.
  - Core Temp: None currently running.
  - OpenRGBTempSync: None currently running.
- **Port 6742**: Verified free via `Get-NetTCPConnection -LocalPort 6742`. No rogue or wildcard listeners present.

## 2. Toolchain and Environment Inventory

| Tool / Package | Expected Pin | Observed State | Notes |
|---|---|---|---|
| Python | 3.12.x | 3.12.10 (64-bit) | Available on PATH. Standard library and core ctypes functional. |
| Pillow | 12.3.0 | 12.3.0 installed | Ready for tray image generation. |
| openrgb-python | 0.3.7 | Not installed in Python 3.12 environment | Pure tests use mock/fixture abstraction; import gates verified. |
| pystray | 0.19.5 | Not installed in environment | Wrapped with runtime fallback / lazy import. |
| .NET SDK | .NET 8.0 | Not on PATH (`dotnet` command not found) | Sensor bridge project and tests created; marked unverified until toolchain present. |
| Inno Setup | 6.7.3 | Not on PATH (`iscc` command not found) | Installer script created; compilation gate documented. |
| PawnIO Driver | 1.0.0 | Driver status unverified | To be verified upon full installer execution. |

## 3. Pinned Dependency Manifest Verification

- **Manifest File**: `third_party/dependencies.lock.json`
- **Validation Suite**: `tests/test_dependency_manifest.py` passed (3/3 tests OK).
- **Verification Script**: `scripts/fetch-vendor.ps1 -VerifyOnly` completed without error.
- **License Notices**: `third_party/THIRD-PARTY-NOTICES.md` records GPL-2.0, GPL-3.0, MPL-2.0, HPND, MIT, and BSD licenses.