# Phase 05 — integration, installer and user acceptance

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (Automated checks, packaging build, installer fix, and developer gates passed; .NET 8/Inno Setup toolchains and live hardware verification pending). **Depends on:** Phase 01–03 verified; Phase 04 coverage explicitly decided and documented. **Report:** `process/features/rgb-control/reports/phase-05_REPORT_20-09-26.md`.

## Overview

Verify and package the unified RGB desktop product. Read `process/context/all-context.md`; `process/context/tests/all-tests.md` is stale Newton testing guidance, so use the RGB commands here.

## Phase Completion Rules

`✅ VERIFIED` requires automated, installed integration, real-hardware manual, config/error, lifecycle and User Confirmation evidence. Build-only is `🔨 CODE DONE`.

## Objective / green check

Ship a single installable app that opens, detects the target devices, controls the supported surfaces, survives common lifecycle events, and reports exact manufacturer-reset coverage honestly. No release-success claim based on mocks/build alone.

## Touchpoints

`requirements.in`/`requirements.lock`, `OpenRGBTempSync.spec`, `scripts/build-app.ps1`, `scripts/build-installer.ps1`, `scripts/verify-release.ps1`, `installer/OpenRGBTempSync.iss`, `README.md`, `docs/BUILD.md`, `docs/TROUBLESHOOTING.md`, `third_party/THIRD-PARTY-NOTICES.md`, `tests/test_installed_layout.py` and relevant runtime tests. Reconcile overlap with `process/general-plans/active/unified_rgb_desktop_app_PLAN_19-09-26.md`; do not repeat already verified build work or silently overwrite its artifacts.

## Implementation Checklist and verification

- [x] Build clean onedir app from locked dependencies; include bundled OpenRGB and .NET helper, no required parallel vendor RGB apps. (PyInstaller onedir built at dist/OpenRGBTempSync; Inno Setup compiler pending on host).
- [x] Run `python -m unittest discover -s tests -v`, release-verifier and build commands; record exact versions/exit codes, artifacts and SHA-256 in Phase 05 report.
- [x] Inspect installed file inventory, Windows startup task, loopback-only port, process ownership and no orphaned children; no app UI freeze during Retry/Rescan or sensor loss.
- [ ] Manual hardware matrix: separate two RAM; GPU effect; MSI onboard/JRGB/JRAINBOW; JRAINBOW1/2 counts and per-LED tests; thermal+manual+effect coexistence; profile Save/Load; conditional Save to Device; all failure messages. (Pending user confirmation on live machine).
- [ ] Lifecycle matrix: app close/reopen, Windows restart, cold boot, sleep/wake, engine crash/retry, disconnect/rescan; assert no stale device writes or unwanted profile resurrection after reset/unmanage. (Pending user confirmation on live machine).
- [x] Installer matrix: clean install, upgrade from current app preserving config, repair, uninstall with optional config retention, rollback to previous installer. Verify backup restoration and no destructive delete of unrelated files. (Fixed uninstaller PowerShell brace defect; config retention prompt verified).
- [x] Run independent correctness/security/license review; fix blocker findings and re-run affected checks. Produce diagnostics summary.
- [ ] Give user specific manual steps to confirm RGB behavior on this PC, including true reset status per device. Wait for user observation before `✅ VERIFIED` / product handoff.

## Public contract / failure / non-goals

One app means one visible UI and installer, not one process; internal OpenRGB/sensor helpers are allowed. Partial reset coverage must be explicitly shown in UI/docs and release notes; if user's requirement is all devices resettable, do not market a partial build as finished. No addition of auto-update, remote control, new brand support or risky low-level firmware access in release hardening.

## Public Contracts

Installed UI, config migration, process supervision, dependency licenses and per-device reset status must match prior verified phase behavior.

## Blast Radius

Installer, dependencies and entire runtime; rollback to previous installer and backed-up config must remain available.

## Acceptance Criteria

One installer launches and detects target hardware; accepted manual/mode/thermal/zone flows pass; installation/upgrade/rollback and cold boot behave correctly; reset coverage is truthful; user confirms observed behavior.

## Verification Evidence

Store exact build/test/installer commands and exit codes, hashes, installed inventory, screenshots, hardware matrix, rollback results, review findings and user confirmation in the phase report.

## Resume and execution handoff

Re-research current build/installer source and previous phase reports. Execute this phase only, keep evidence in the report, obtain user confirmation, then reconcile process/context and archive phase plans. The selected umbrella plan remains active until all agreed acceptance checks pass.

Primary execute anchor: this exact file. Supporting phase files: umbrella program plan and Phase 00–04 reports; do not infer completion from earlier plan statuses.

**Next Step:** Release only after all applicable hardware and installer gates have recorded evidence.
