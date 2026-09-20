# Phase 6 — Release, Regression, and Target-Hardware Acceptance

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phases 1–5 closed honestly; Phase 5 may contain unsupported families but release claims must match  
**Report:** `process/features/unified-rgb-control/reports/phase-6-release-acceptance_REPORT_20-09-26.md`

## Objective

Package and validate the redesigned app as one Windows product. Prove upgrade safety, runtime stability, UI usability, target-hardware behavior, restart/sleep/reboot handling, and truthful reset support wording.

## Touchpoints

Modify as needed: `requirements.lock`, `scripts/build-app.ps1`, `scripts/build-installer.ps1`, `scripts/verify-release.ps1`, `installer/OpenRGBTempSync.iss`, `tests/test_installed_layout.py`, `tests/test_dependency_manifest.py`, README/build/troubleshooting/third-party docs, version metadata. Product source changes are limited to release blockers discovered in validation and must be reconciled with the owning phase plan.

## Release Checklist

- [ ] Freeze versions/hashes and regenerate dependency/license notices, including PySide6/Qt and any approved OpenRGB client change.
- [ ] Run all Python and .NET tests plus dependency, installed-layout, and release verification scripts.
- [ ] Build twice from clean staging and compare expected artifact inventory; explain non-deterministic metadata.
- [ ] Verify only required Qt plugins/modules are shipped and app launches on a clean Windows 11 x64 account.
- [ ] Test fresh install, upgrade from 1.0.0/current installed build, reinstall/repair, cancelled install, uninstall keeping settings, optional settings removal, and previous-installer rollback.
- [ ] Verify v2→v3 migration backup, duplicate RAM resolution, profiles, zone counts, aliases, and rollback instructions.
- [ ] Verify one Start Menu entry, one tray icon, one scheduled task, one app-owned OpenRGB process tree, loopback-only SDK, and no orphan processes.
- [ ] Execute the hardware matrix below sequentially with other RGB owners closed.
- [ ] Run disconnect/reconnect, OpenRGB child crash/restart, sensor bridge crash/restart, stale sensor, screen saver, lock/unlock, sleep/wake, reboot, and cold boot.
- [ ] Run 30-minute thermal soak and 500-interaction UI/command stress; record CPU/memory/queue/UI latency and errors.
- [ ] Review every use of `reset`, `default`, `original`, `saved`, and `supported` in UI/docs/logs for truthfulness.
- [ ] Obtain user acceptance screenshots/video and explicit confirmation.

## Target Hardware Matrix

| Surface | Required checks |
|---|---|
| Two ENE RAM devices | distinct identity; RAM A red/RAM B blue; individual selection where supported; effect capability; reconnect/reorder; profile round trip; reset status truthful |
| MSI MAG B550 TOMAHAWK | JRGB1/2 whole-zone behavior; JRAINBOW1/2 independent counts and LED selection; ONBOARD; controller-wide effect scope; thermal/manual/effect transitions; reset status/proof |
| Gigabyte AORUS RTX 3060 ELITE LHR | zone inventory; supported manual scope; representative hardware effects; temperature while another device uses another owner; reset status/proof |
| Sensors | CPU/GPU readings; stale/missing state; no silent source fallback; smooth thermal recovery |
| Windows lifecycle | first launch, tray reopen, second-instance activation, startup task, lock, screen saver, sleep, wake, restart, cold boot, exit |

## Acceptance Criteria

- Device tree consistently shows two independently controllable RAM entries.
- Manual device/zone/LED writes affect only advertised target scope.
- JRAINBOW counts survive app restart, OpenRGB reconnect, and reboot with exact readback.
- Hardware-effect controls match live capabilities and never promise unsupported per-zone independence.
- Thermal mode retains current gradient/EMA behavior and coexists with other devices’ owners.
- Profiles activate deterministically and report partial/unresolved targets.
- Manufacturer reset is enabled only for exact verified families; successful labels have cold-boot/profile-independent proof; unsupported families cannot be invoked.
- No concurrent SDK writes, queue growth, UI freeze, orphan child, wildcard listener, config loss, or repeated device-flash write.
- Installer upgrade preserves data; rollback procedure restores previous app safely.

## Test Commands

- `python -m unittest discover -s tests -p "test_*.py" -v`
- `dotnet test sensor-bridge.Tests/OpenRGBTempSync.SensorBridge.Tests.csproj`
- `powershell -ExecutionPolicy Bypass -File scripts/verify-release.ps1`
- Build/installer commands documented by existing scripts, run from clean staging.

Exact outputs and exit codes go in the report. If a release blocker requires product code changes, return to the owning phase, update its report/status, fix, and repeat affected regression gates.

## Rollback

Retain previous signed/hashed installer, v2/v3 config backups, OpenRGB config export, dependency manifest, and uninstall log. Rollback never writes manufacturer reset or device flash. If v3 cannot be consumed by the old build, restore the preserved v2 backup rather than mutating v3.

## Blast Radius

Distribution, upgrade/uninstall, all hardware behavior, and user claims. Treat any mismatch between docs and evidence as a release blocker.

## Verification Evidence

All test logs, artifact hashes/inventory, install/upgrade/uninstall screenshots, process/port checks, config migration diff, hardware matrix evidence, performance logs, reboot/sleep records, reset support matrix, and user acceptance.

## Resume and Execution Handoff

Assign a release executor, independent tester, and final code reviewer. Use this phase as the only execute anchor. Final status remains `🧪 TESTING` until the user completes hardware and cold-boot steps. After acceptance, enter UPDATE PROCESS to archive phase plans and capture durable RGB context.
