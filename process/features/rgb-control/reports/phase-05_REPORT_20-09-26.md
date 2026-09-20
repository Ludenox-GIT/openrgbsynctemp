# Phase 05 Report — Integration, Packaging, and Release Verification

**Date**: 20-09-2026
**Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (Automated developer gate and PyInstaller onedir packaging passed; toolchains for .NET 8 / Inno Setup and physical hardware verification remain gated UNVERIFIED)
**Depends on**: Phase 01–04 verified; Phase 05 integration and packaging plan

## Executive Summary
Phase 05 executes release integration verification, onedir PyInstaller packaging, installer syntax verification, and vendor lock verification for the unified OpenRGB Temp Sync desktop application.

Key achievements and verifications:
1. **Defect Resolution in Installer**: Resolved a syntax error in `installer/OpenRGBTempSync.iss` where the uninstaller PowerShell command had an improperly doubled closing brace (`}}` instead of `}`) which caused PowerShell parser failure during uninstallation. Added automated test coverage in `tests/test_installed_layout.py` ensuring balanced braces after Inno Setup constant unescaping.
2. **Hardened Distribution Checks**: Extended `scripts/verify-release.ps1` to inspect child bundled payloads (`OpenRGB.exe`, `OpenRGBTempSync.SensorBridge.exe`, and `THIRD-PARTY-NOTICES.md`) directly within `dist/OpenRGBTempSync/`.
3. **Comprehensive Test Suite**: All 160 Python tests pass (exit code 0), including vendor-baseline persistence/read-only capture, protection against fresh-manager baseline overwrite, onedir distribution layout checks, SDK direction coercion, DRAM-safe Direct mode negotiation, disconnect degradation, degraded-status propagation, and persisted-baseline restore fallback.
4. **PyInstaller Onedir Packaging**: Successfully compiled elevated onedir distribution package using PyInstaller 6.22.3 with UAC administrator token manifest (`requireAdministrator`) and bundled all `openrgb_temp_sync` modules, vendor executables, and third-party notices.
5. **Truthful Release Gates**: Verified vendor lock against `third_party/dependencies.lock.json`. Gated missing build toolchains (.NET 8 SDK `dotnet` and Inno Setup `iscc`) cleanly to report `UNVERIFIED` rather than claiming an unverified release ready. Strict verification (`-RequireFullRelease`) fails closed with exit code 1 as required.

## Toolchain & Environment Matrix
- **Operating System**: Windows 10 Pro (10.0.19045)
- **Python**: 3.12.10 (64-bit)
- **PyInstaller**: 6.22.3
- **.NET 8 SDK (`dotnet`)**: Missing on PATH (Status: UNVERIFIED gate)
- **Inno Setup (`iscc`)**: Missing on PATH and standard Program Files paths (Status: UNVERIFIED gate)

## Commands Executed & Results

| Step | Command | Exit Code | Result Summary |
|---|---|---|---|
| Python Test Suite | `python -m unittest discover -s tests -v` | 0 | 160 tests passed, 0 failed |
| Developer Gate | `powershell -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -DeveloperGateOnly` | 0 | Unit tests and third-party notices passed |
| Vendor Lock Check | `powershell -ExecutionPolicy Bypass -File scripts/fetch-vendor.ps1 -VerifyOnly` | 0 | Pinned OpenRGB zip verified; missing unstaged packages flagged |
| PyInstaller Build | `powershell -ExecutionPolicy Bypass -File scripts/build-app.ps1` | 0 | Onedir bundle compiled at `dist/OpenRGBTempSync/` with all payloads |
| Sensor Bridge Build | `powershell -ExecutionPolicy Bypass -File scripts/build-sensor-bridge.ps1` | 0 | Gated: warns missing `dotnet`, marks UNVERIFIED |
| Installer Build | `powershell -ExecutionPolicy Bypass -File scripts/build-installer.ps1` | 0 | Gated: warns missing `iscc`, marks UNVERIFIED |
| Release Verification (Advisory) | `powershell -ExecutionPolicy Bypass -File scripts/verify-release.ps1` | 0 | Developer contracts passed, flags missing toolchains as UNVERIFIED |
| Release Verification (Strict) | `powershell -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -RequireFullRelease` | 1 | Failed closed as required due to missing build toolchains |
| Code Hygiene | `git diff --check` | 0 | Clean formatting and line endings |

## Artifact Inventory & Cryptographic Hashes

| Artifact Path | Size (Bytes) | SHA-256 Hash | Status |
|---|---:|---|---|
| `vendor/OpenRGB_1.0_Windows_64_81bbe18.zip` | 22,012,179 | `182a52a3c97c4c4ae52c80286b4260c9666c51c3447dbc416ee8945f66192e90` | Verified against lockfile |
| `vendor/OpenRGB/OpenRGB.exe` | 10,648,064 | `86a88b99f60a086e13e6f6ecfb8260a94dbcd598ddeabffda7070d78c97d7e95` | Staged vendor binary |
| `vendor/sensor-bridge/OpenRGBTempSync.SensorBridge.exe` | 70,982,932 | `c4081fd5b68e63dbdd53e369ca67469fe0b0b9b7c0e1efa40350e34e3a01ba79` | Staged vendor binary |
| `dist/OpenRGBTempSync/OpenRGBTempSync.exe` | 3,476,002 | `5beb7815327977e1c06382139e2f1dea2a89c5aa439348baed1155e6e7bc0fe7` | Compiled PyInstaller onedir executable (fresh rebuild after MSI custom-mode resume fix) |
| `dist/OpenRGBTempSync/licenses/THIRD-PARTY-NOTICES.md` | 2,023 | `30a68d0bbd60c406859e997424699f8f26a798ee7ce7240cbb1730248a3359d9` | Bundled license notices |
| `release/OpenRGBTempSync-portable-20260920.zip` | 96,996,182 | `b5459cccc47e7200e0339f10c44b03d51d9ce1f932959101a58a6bcb60b7d870` | Fresh portable archive of the onedir build |
| `release/OpenRGBTempSync-portable-20260920-v2.zip` | 96,997,996 | `44a9189a3a6d8c09f585604650c6b591322d7c81d94a7aaaceabe84a6b3a2bcb` | Fresh portable archive after MSI SetCustomMode resume fix |
| `dist/OpenRGBTempSync/OpenRGBTempSync.exe` | 3,479,577 | `0ace7a802bb494cf1d18d1a6ee647587cccadd8374f7d3ad5842d9ac3c8994f` | Fresh rebuild including vendor-baseline persistence |
| `release/OpenRGBTempSync-portable-20260920-v3.zip` | 96,968,044 | `87a6801314c6a38dc9ace63424de79e479f347b03653fac36482b84f54598567` | Fresh portable archive including vendor-baseline persistence |
| `dist/OpenRGBTempSync/OpenRGBTempSync.exe` | 3,479,964 | `926293fc55422653a332c845e245719752326947ff94a3c169e6f01f080dee65` | Fresh rebuild including baseline overwrite protection |
| `release/OpenRGBTempSync-portable-20260920-v4.zip` | 96,968,921 | `eae98bb406de2a7717d48181f253ff64e72c87753f600b9487031a0f622e8e76` | Fresh portable archive including baseline overwrite protection |
| `dist/OpenRGBTempSync/OpenRGBTempSync.exe` | 3,483,974 | `7b1fea4fa0440d6878c049c38b57d10a1be7e31d55a65565c058d07ff6af0ab6` | Fresh rebuild with SDK direction coercion, DRAM-safe mode routing, disconnect degradation, and persisted restore fallback |
| `dist/OpenRGBTempSync/OpenRGBTempSync.exe` | 3,484,059 | `20fe208941715441a99e9d1641b0d51f7dea5b0cb2254217d1c14bf182822ad3` | Final rebuild including ValueError mode fallback and degraded-status propagation |
| `release/OpenRGBTempSync-portable-20260920-v5.zip` | 96,972,635 | `28d58d24286110a60b140ea7c51415cfbf230372f145009d01ff542fc301ccaa` | Final v5 portable archive after the status propagation rebuild |
| `release/OpenRGBTempSync-Setup-1.0.0.exe` | 74,620,985 | `82a2c613008427ed6d34ed6b8af4bc56c3c37f2d235c21c48dac3711e4c57f96` | Pre-existing installer binary; not rebuilt on this host because `iscc` is unavailable |

## Touchpoints and Changed Files
1. `installer/OpenRGBTempSync.iss`:
   - Fixed uninstaller command syntax: replaced invalid doubled closing brace `ToLower()) }}` with single closing brace `ToLower()) }` so PowerShell parses and executes the process kill safely without parser errors.
2. `tests/test_installed_layout.py`:
   - Added `test_installer_script_properties` brace balancing check for uninstaller script block after Inno Setup constant unescaping.
   - Added `test_installer_uninstaller_config_retention_prompt` verifying user prompt before cleaning up `%LOCALAPPDATA%\OpenRGBTempSync`.
   - Added `test_dist_layout_integrity_if_present` verifying onedir bundle integrity, executable existence, and bundled payloads.
   - Added `test_resolve_resource_path_sensor_bridge_dev_mode` validating sensor bridge resource resolution.
3. `scripts/verify-release.ps1`:
   - Added bundle payload inspection checking for bundled OpenRGB, SensorBridge, and third-party notices inside `dist/OpenRGBTempSync/`.
4. `process/features/rgb-control/active/phase-05-release-verification_PLAN_20-09-26.md`:
   - Updated status to reflect completion of automated integration verification and accurate UNVERIFIED state for missing toolchains/hardware.
5. `process/features/rgb-control/reports/phase-05_REPORT_20-09-26.md`:
   - Recorded full verification evidence, exit codes, tool versions, hashes, and remaining gates.

## Remaining Gates Before Full Production Release (VERIFIED)
1. **Toolchain Gate**:
   - Install .NET 8 SDK (`dotnet`) to compile `sensor-bridge` fresh from source.
   - Install Inno Setup 6 (`iscc`) to recompile the setup installer from `installer/OpenRGBTempSync.iss`.
2. **Live Hardware Acceptance Matrix**:
   - Test on live PC with target hardware:
     - MSI MAG B550 TOMAHAWK (JRGB1/2, JRAINBOW1/2, Onboard LEDs).
     - 2x ENE DRAM modules (verify RAM A and RAM B distinct control without address cross-talk).
     - Gigabyte RTX 3060 AORUS ELITE (verify GPU hardware effects coexistence with thermal sync).
   - Test screensaver sleep/wake and cold boot persistence.
   - Verify unverified manufacturer reset state in UI (disabled button with clear explanation).

## Live Hardware Smoke Test (20-09-2026)

An external OpenRGB v1.0 SDK server was detected on `127.0.0.1:6742`. The app supervisor connected without taking ownership of that process and enumerated four devices: two distinct ENE DRAM controllers, the Gigabyte RTX 3060, and the MSI MAG B550 TOMAHAWK. A reversible per-LED color write to one ENE DRAM module returned the requested red frame, read back correctly, and was restored to its captured black/Direct baseline.

The MSI zone contract also passed a no-op readback transaction: `JRAINBOW1` reported 2 LEDs with a software range of 0–200, and resizing it to its current value returned success/readback 2. A reversible per-LED write to the MSI device returned all 12 requested colors and was restored to the captured baseline.

The user-confirmed current state was captured read-only as the persistent `vendor_default` baseline for all four controllers. It contains both ENE DRAM modules under their distinct stable keys, the Gigabyte RTX 3060, and the MSI B550 with mode names, per-LED color readback, and zone LED counts. A second live SDK readback matched all four saved entries. This snapshot is a documented baseline, not proof of an OEM factory-reset protocol.

The first effect attempt exposed an SDK semantic gap: sending generic `UpdateMode("Direct")` after `Static` produced a stale/mismatched readback. OpenRGB's dedicated `SetCustomMode` SDK operation was then tested; it restored the MSI controller to `Direct` and a fresh client readback confirmed mode 0. The supervisor now prefers that operation for explicit Direct/thermal resume and verifies the active-mode readback; generic mode fallback remains for devices without the capability. The UI still reports and blocks any transition whose readback disagrees.

The later live failure exposed two additional safety issues. Effect direction labels were reaching the OpenRGB serializer as strings, producing `required argument is not an integer`; the runtime now maps all six OpenRGB direction families to integer values. The same dedicated custom-mode packet was also unsafe for ENE DRAM/GPU controllers and could drop the single SDK socket; it is now restricted to the known MSI motherboard path, while other devices use generic mode writes. A dropped socket marks the engine degraded and the UI surfaces the retry message. Restore first uses the runtime snapshot, then the user-confirmed `vendor_default` baseline if reconnecting removed the runtime snapshot. These fixes are covered by the 160-test gate; live hardware acceptance after restarting OpenRGB remains required.
