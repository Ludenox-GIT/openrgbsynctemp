# Phase 02 — device UI, manual color and Edit Zone

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (automated UI/zone contracts pass; full user hardware confirmation remains pending). **Depends on:** Phase 01 verified. **Report:** `process/features/rgb-control/reports/phase-02_REPORT_20-09-26.md`.

## Overview

Implement OpenRGB-like selection and Edit Zone UI. Read `process/context/all-context.md` and treat `process/context/tests/all-tests.md` as stale Newton-specific guidance, not the RGB test runner.

## Phase Completion Rules

`✅ VERIFIED` requires integration, real-hardware manual test, readback, error handling and User Confirmation; build/code alone is `🔨 CODE DONE`.

## Objective / green check

OpenRGB-like control surface for this PC: device → zone → LED selection; manual RGB/HSV/Hex color; independent LED counts for JRAINBOW1/2. Green proves real physical output and persistent counts, not hardware effects or factory reset.

## Touchpoints / architecture

Replace `src/openrgb_temp_sync/ui.py` Tk settings implementation with a PySide6 UI only after confirming licensing/package size/build viability; keep a small adapter for tray/show calls in `src/openrgb_tray_app.py` and `windows_runtime.py`. Add the fewest UI modules needed for device tree, LED grid and Edit Zone dialog; no UI-owned SDK client. Update `requirements.in`/`requirements.lock`, `OpenRGBTempSync.spec`, `scripts/build-app.ps1` and tests. If PySide6 viability fails, return to plan with a justified Tk path rather than speculative framework churn.

## UI contract

Tree left: stable RAM A/B labels, GPU, MSI motherboard expandable to JRGB1/2, JRAINBOW1/2, ONBOARD. Selection center: entire device, zone, single/multi LED with clear numeric indices and Select All. Right: `Manual | Effects | Temperature` tabs; only Manual is active in this phase, others show honest pending/available status. Color wheel + RGB/HSV/Hex, preset swatches, scope preview, Apply. Header shows connection/temperature freshness and Rescan; footer has app profile status/diagnostics. Accessible keyboard focus, scalable high-DPI layout, no blocking SDK calls on UI thread, helpful empty/disconnected states. Cancel discards staged edits; Apply writes once and reports result; no silent persistence success.

## Edit Zone contract

Only resizable zones have enabled action. Show current/min/max from live descriptor and number input; do not request fan model/count as prerequisite. Both JRAINBOW headers have distinct keys/counts. On Apply, worker pauses target controller writes, validates integer/range, calls SDK resize, re-reads zone count, accepts only exact match, saves config, refreshes grid. On Cancel no device/config write. Optional “Find LED” is a temporary user-triggered test with bounded time and rollback of preview state. Clarify software count vs power wiring; JRGB is one logical channel and has no per-bulb editor. For a parallel hub, one logical LED may light multiple fans together; represent what hardware actually allows.

## Implementation Checklist and tests

- [ ] Add failing UI-model tests for two identically named RAM items, unique zone keys, empty/zero LED zone, multi-select and capability-disabled controls.
- [ ] Verify UI dependency/install/build feasibility; pin versions and notices only after proof.
- [ ] Build device tree, selection model and live capability rendering; add UI-thread responsiveness test around rescan/retry.
- [ ] Build Manual panel, validate color numeric/Hex input and scope; write only via dispatcher; assert one selected LED does not recolor others.
- [ ] Add Edit Zone dialog with staged changes, min/max validation, readback and exact-count persistence; test 0→N, N→M, invalid/overflow, failed SDK write, readback mismatch and Cancel.
- [ ] Fix stale inventory refresh and original Tk widget-reference defect by replacing code path; ensure Save reports failure and Cancel semantics are consistent.
- [ ] Run Python tests and build smoke; capture window screenshots at 100% and 150% scaling. On user's hardware, verify RAM A red/RAM B blue; JRAINBOW1 and JRAINBOW2 separately configured and visually lit; JRGB changes entire physical chain, not imaginary per-LED.

## Failure / rollback / proof

Do not auto-apply an arbitrary LED count. If a header is detected but dark after count change, show diagnostic steps (mode, hub power/path, LED count, other RGB controller conflict), not a false “done”. Previous installer/config backup remain rollback path. Real-hardware proof requires before/after images or short user observation and readback after app restart. No vendor reset in this phase.

## Public Contracts

UI reads immutable descriptors and sends typed commands to the Phase 01 dispatcher; it owns no SDK client. Edit Zone accepts only live, resizable zone keys and reports actual count readback.

## Blast Radius

UI framework, packaged assets and user control surface; hardware writes remain behind the dispatcher.

## Acceptance Criteria

The device tree distinguishes both RAM; manual selection affects only the chosen device/zone/LED; both JRAINBOW headers support independent count edit with exact readback and persistence; UI remains responsive; Cancel performs no write.

## Verification Evidence

Record Python/build test commands, screenshots at 100%/150% scaling, actual LED/count observations, readback after restart, and user confirmation in the phase report.

## Agent handoff

UI worker gets this file plus umbrella and Phase 01 report; independent tester checks keyboard/high-DPI and hardware targeting. Next: `phase-03-modes-thermal-profiles_PLAN_20-09-26.md`.

## Resume and Execution Handoff

Primary execute anchor: this exact file. Supporting phase files: umbrella program plan plus Phase 00–01 reports. Preserve current installer/config and re-research UI dependency viability.

**Next Step:** Execute this phase only after Phase 01 is verified and re-research/approval are complete.
