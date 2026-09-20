# Phase 2 — PySide6 Device → Zone → LED UI and Manual Color

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phase 1 `✅ VERIFIED`  
**Report:** `process/features/unified-rgb-control/reports/phase-2-ui-manual-color_REPORT_20-09-26.md`

## Objective

Replace the fixed 500×600 Tk settings window with a scalable PySide6 workspace modeled on OpenRGB’s useful hierarchy. Deliver capability-aware manual color control for device, zone, one LED, or multiple LEDs while retaining tray integration and avoiding direct SDK access from UI code.

## Touchpoints

Modify: `src/openrgb_tray_app.py`, `requirements.in`, `requirements.lock`, build/release scripts and installer only as required for Qt packaging.  
Add: `src/openrgb_temp_sync/desktop_ui.py` and focused UI model/delegate modules only when one file becomes unmaintainable.  
Retire after cutover: `src/openrgb_temp_sync/ui.py` from production imports; keep temporary compatibility only within this phase.  
Tests: add `tests/test_ui_model.py`, `tests/test_manual_color_commands.py`, update installed-layout/dependency tests.

## Public Contracts

- UI reads snapshots/state events and submits commands; it never receives mutable OpenRGB objects.
- Selection is a list of stable ids with a deterministic summary and capability intersection.
- Color input normalizes RGB/HSV/Hex into one RGB value; invalid input never submits.
- Apply scope is explicit. Mixed-capability selection disables unsupported actions with an explanation.

## Required UI Behavior

- Left pane lists devices with aliases, type icons, status, expandable zones, and duplicate-name disambiguation.
- Center pane shows breadcrumb, Manual/Effect/Temperature tabs, zone selector, Edit Zone availability, LED tiles, select-all, Ctrl/Shift multi-select, and ownership/status banner.
- Right pane shows color wheel, value/saturation square, RGB/HSV/Hex fields, swatches, brightness only when implementable without misleading the user, and Apply.
- Bottom bar contains Apply to selection, Apply to selected devices, Save app profile, conditional Save to Device, diagnostics/status, and Device Maintenance.
- Keyboard navigation, visible focus, screen-reader labels, DPI scaling at 100/125/150/200%, minimum window size, and high-contrast readability are acceptance requirements.
- Closing the window hides to tray; exiting the tray performs deterministic dispatcher shutdown.

## Implementation Checklist

- [ ] Add UI-model tests for device tree ordering, duplicate labels, zone/LED membership, selection intersections, and stale snapshot reconciliation.
- [ ] Pin the smallest supported PySide6 distribution and regenerate lock; document package-size change and included Qt plugins.
- [ ] Implement one `QApplication` lifecycle compatible with pystray and the existing single-instance activation path; marshal all UI changes through Qt signals.
- [ ] Implement device tree and breadcrumb from immutable snapshots; preserve selection where ids survive refresh.
- [ ] Implement LED tile/grid virtualization or lazy rendering for large zones; target smooth interaction at 500 logical LEDs without creating one heavyweight widget per refresh.
- [ ] Implement color model synchronization and validation for RGB, HSV, Hex, wheel, swatches, and staged preview.
- [ ] Implement selection-to-command translation for device, zone, single LED, and multi-LED; submit through dispatcher only.
- [ ] Require confirmation before applying to multiple devices and summarize unsupported/skipped targets before submission.
- [ ] Implement typed result display: applied count, unsupported targets, retryable failure, fatal/degraded device.
- [ ] Port current thermal settings and diagnostics into PySide6 without changing their behavior yet.
- [ ] Remove the Tk initialization-order defect by eliminating the old production view; do not patch around `zone_controls_frame = None` as the final UI architecture.
- [ ] Update build scripts, PyInstaller collection rules, installer size checks, installed-layout tests, and third-party notices for Qt.
- [ ] Add UI automation/model tests that do not require OpenRGB hardware; add screenshot/manual checks for the supplied OpenRGB-like layout.
- [ ] Run live approved tests: RAM A red/RAM B blue independently; one motherboard zone color; one GPU supported scope; one LED-only change where capability says per-LED.

## Tests

- Targeted Python unit tests for UI models and command construction.
- Full Python suite.
- Headless/offscreen smoke: launch, populate fake snapshot, select scopes, submit command, receive result, close/reopen.
- Packaging smoke: installed executable launches without missing Qt platform plugin.
- Manual DPI/accessibility matrix and target-hardware color matrix.

## Rollback

Keep no dual production UI after acceptance. Before acceptance, previous installer remains rollback. Config v3 is shared; UI migration must not mutate lighting settings simply by opening or cancelling.

## Blast Radius

Desktop event loop, tray/window integration, dependencies, package size, installer contents, and all user-facing settings. Hardware writes remain protected by Phase 1 dispatcher.

## Verification Evidence

UI test logs, package diff, screenshots at four scale factors, keyboard checklist, installed launch log, command/result logs, and target-hardware photos.

## Resume and Execution Handoff

Use a UI/UX execution specialist and a separate tester. Re-research pystray/Qt lifecycle and current packaging first. Do not add effects, profile semantics, zone resize, or factory reset beyond disabled/navigation placeholders.
