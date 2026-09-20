# Unified RGB Control — program plan

**Date**: 20-09-2026  
**Complexity**: Complex phase program  
**Status**: 🔨 CODE DONE / 🧪 UNVERIFIED — implementation and automated verification completed through Phase 05; live hardware, cold-boot and exact manufacturer-reset proof remain pending.

## Overview

Deliver one installed Windows app controlling the current PC's two ENE/G.SKILL RAM modules, Gigabyte AORUS RTX 3060 ELITE LHR, and MSI MAG B550 TOMAHAWK (MS-7C91): device → zone → LED manual color, supported hardware modes, existing temperature-driven lighting as a selectable mode, independently editable JRAINBOW1/2 LED counts, app profiles, and **genuine manufacturer-default restoration when proven per device**. One UI and installer may contain bundled OpenRGB and sensor helper; no requirement to rewrite hardware drivers. Do not advertise a universal factory reset unless every targeted device has passed its own proof gate.

This program extends, but does not supersede, `process/general-plans/active/unified_rgb_desktop_app_PLAN_19-09-26.md`. That older plan covers one-app runtime, sensor bridge and installer; its implementation state must be audited before reuse. Avoid duplicate work and maintain existing installer/config compatibility. The repo has a dirty worktree; inventory and preserve all user changes before implementation.

## Phase Completion Rules

Each phase requires integration verification, manual user flow on the applicable hardware, state/config readback, failure-case checks and **User Confirmation**. `⏳ PLANNED` = not started; `🔨 CODE DONE` = implemented without full proof; `🧪 TESTING` = proof underway; `✅ VERIFIED` = phase gates, overlapping regressions and user-confirmed behavior passed; `🚧 BLOCKED` = real stop condition documented. No phase advances on a green mock suite alone. Read `process/context/all-context.md` for repo routing and note `process/context/tests/all-tests.md` is stale Newton/Vite guidance; this plan's Python/.NET commands govern RGB work until context is reconciled.

## Existing truth and sources

- Runtime entry point: `src/openrgb_tray_app.py`; Python package: `src/openrgb_temp_sync/`; .NET sensor bridge: `sensor-bridge/`; installer: `installer/OpenRGBTempSync.iss`.
- Current Tk settings UI is thermal-centric. In `ui.py`, zone/reset widget references created in `_setup_advanced_tab` are overwritten with `None` at lines 166–167; zone controls therefore do not render. Fix underlying lifecycle, not only the visible label.
- Current `restore_device` / `reset_device_to_original` restore an in-memory pre-sync snapshot. Rename this distinctly; it is **not** manufacturer reset.
- Name-keyed state and first-match lookup collide for the two `ENE DRAM` devices. Reset/resize/thermal writes may address the wrong RAM.
- Baseline gaps were addressed in the implementation: resume negotiates OpenRGB custom/Direct mode with readback, thermal/lights-off writes route through supervisor serialization with ownership guards, duplicate RAM targets reject ambiguous names, and Edit Zone persists only after exact readback. Remaining proof gates are live mode/cold-boot behavior and an actual OEM reset path; the release artifact is intentionally marked `UNVERIFIED` until those gates are confirmed.
- Installed SDK is `openrgb-python==0.3.7`, currently speaks protocol 4. `Zone.resize()` already refreshes parent device data; missing step is explicit requested-vs-readback verification and serialized write state. Do not claim it lacks refresh.
- Pinned bundled OpenRGB source commit: `81bbe18a84c2e507006f19dd252e397e40a56bfe`. Relevant upstream files: `qt/OpenRGBDevicePage/OpenRGBDevicePage.cpp`, `qt/OpenRGBZoneEditorDialog/OpenRGBZoneEditorDialog.cpp`, `RGBController/RGBController.{h,cpp}`, `Documentation/OpenRGBSDK.md`, and `Controllers/MSIMotherboardController/MSIMotherboard185Controller/*`.
- OpenRGB's B550 TOMAHAWK definition exposes JRGB1, JRGB2, JRAINBOW1, JRAINBOW2, ONBOARD. JRGB is one logical color channel per header; JRAINBOW is addressable. Driver software limits JRAINBOW1=200 and JRAINBOW2=240, **not** electrical safety limits. Configured count can start at 0 without proving no physical LEDs. Both headers are connected on the user's PC.
- MSI SDK publicly documents color/style/brightness/speed, not universal factory reset, and depends on Mystic Light being installed. G.SKILL's Reset resets software effect settings; cold-boot rainbow is the RAM's default behavior. GPU/MSI genuine reset remains unproven. No blind EEPROM write, firmware reflash, CMOS clearing, or vendor packet replay.

Primary upstream references: [OpenRGB SDK](https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Documentation/OpenRGBSDK.md), [MSI OpenRGB controller](https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Controllers/MSIMotherboardController/MSIMotherboard185Controller/RGBController_MSIMotherboard185.cpp), [OpenRGB Zone Editor](https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/qt/OpenRGBZoneEditorDialog/OpenRGBZoneEditorDialog.cpp), [MSI SDK PDF](https://storage-asset.msi.com/files/pdf/Mystic_Light_Software_Development_Kit.pdf), [G.SKILL software guide](https://www.gskill.com/gskill-device/memory/guides/Trident_Z_Lighting_Control_Software_Guide_1.19g.pdf).

## Architecture decisions

1. Retain OpenRGB as the only hardware backend and the existing Python thermal/sensor/runtime code where sound. Do not add MSI Center, RGB Fusion, or G.SKILL software as runtime dependencies merely to gain modes/reset; that breaks the one-app goal.
2. A capability snapshot is the UI contract: device identity, zones/count/ranges, mode flags and settings, save capability, and reset-support status. Never show a control as usable merely because another device supports it. Version-gate SDK/protocol features; protocol 4 support must be tested, not assumed equivalent to OpenRGB GUI/protocol 6.
3. Every device has exactly one app ownership state: `unmanaged`, `manual_direct`, `hardware_mode`, `thermal_direct`, or `resetting`. Screensaver/off is a separate temporary overlay, not an owner. A mode transition must quiesce old writes, set new device mode, apply new state, verify response, then publish state. No implicit CPU fallback for a missing GPU sensor.
4. Exactly one command dispatcher serializes **all** SDK writes: thermal frame, mode changes, colors, resize, save-to-device, lights-off, stop/retry, reset. UI and sensor threads send commands; neither writes hardware directly. Re-fetch device/zone objects after rescan/resize; reject stale selections.
5. Stable app device keys derive from all available controller metadata plus physical topology/serial where exposed. OpenRGB controller index is session-only. When identical RAM modules remain ambiguous, establish a tested binding using connection/topology evidence or guided one-at-a-time identification; never guess or silently use the first name match. Preserve unresolved legacy name-keyed config and ask for mapping on first migration. Zone keys are device key + zone identity, not global zone name.
6. Proposed UI: PySide6 native desktop window because device tree, scalable LED grid and worker-safe signals are needed. Reuse existing backend and tray operations. Prove packaging/licensing/build impact before switching from Tk; if PySide6 imposes disproportionate release risk, update plan explicitly rather than silently rewriting the product stack.
7. App profile persistence, OpenRGB per-mode `Save to Device`, pre-sync snapshot restore, and genuine manufacturer default are four different operations. UI labels and tests must distinguish them. No flash writes at 20 Hz.

## Public contracts

- `DeviceKey` is persistent and unique within an inventory. `DeviceDescriptor` has immutable key, display name, type, connection metadata, capabilities and fresh zone descriptors. If identity is ambiguous, writes are disabled with actionable status.
- `ZoneDescriptor` has stable parent key, name, OpenRGB index for current session, type, `led_count`, `leds_min`, `leds_max`, `resizable`, and flags. Count is software-addressable LEDs, not hub topology or power budget.
- `LightingAssignment` targets a device or zone/LED selection and has exactly one owner mode. Thermal configuration retains existing curve semantics; manual colors/effect parameters persist separately.
- `WriteResult` reports `ok`, actual readback/status, and a structured failure (`unsupported`, `ambiguous`, `disconnected`, `stale_selection`, `timeout`, `write_failed`, `verification_failed`). Never return true just because SDK method did not raise.
- `FactoryResetCapability` is `verified`, `unverified`, or `unsupported` per exact device/firmware path. Only `verified` enables the user-facing manufacturer reset. `unverified` is not success.
- Config migration is versioned, backed up, atomic and reversible. Preserve unmatched legacy data. One-device-per-name data cannot be auto-applied to both same-name RAM modules.

## UI and behavior contract

Left: rescan/status and tree of RAM A, RAM B, GPU, mainboard → JRGB1/2, JRAINBOW1/2, ONBOARD. Center: selection scope `device/zone/one or multiple LED`; LED grid with index, drag/range and Select All; zone Edit count action only for resizable zones. Right: `Manual color | Hardware effects | Temperature` panels. Manual includes wheel, RGB/HSV/Hex and brightness if available. Hardware effects list and speed/direction/color/brightness are generated from mode flags. Thermal shows live sensor freshness, curve and assigned targets. Bottom: Apply, Save app profile, conditional Save to Device, diagnostics and device management. Keep keyboard navigation, high-DPI and Vietnamese labels; offer readable unsupported reasons.

Edit Zone transaction: pause writes to affected controller; validate integer within OpenRGB range; show warning that software maximum is not header power rating and no auto-detection of physical LED count is guaranteed; resize only chosen JRAINBOW; request/read updated inventory and compare exact count; persist only after success; refresh LED grid and selection; on failure retain previous saved count, report error and rescan. Optional temporary single-LED locator is bounded, user-triggered, and restores previous state when canceled. Shared/parallel hub behavior can cause several physical fans to mirror one address; do not infer fan topology from software count.

## Phased Delivery Plan

| Phase | Anchor | Green proves | Report destination |
|---|---|---|---|
| 00 | [Capabilities and reset feasibility](phase-00-capabilities-reset_PLAN_20-09-26.md) | Inventory, supported mode/zone data and per-device reset evidence matrix are recorded; unknowns remain explicit | `process/features/rgb-control/reports/phase-00_REPORT_20-09-26.md` |
| 01 | [Identity and serialized core](phase-01-identity-serial-core_PLAN_20-09-26.md) | Duplicate RAM cannot collide; mode/write/resize/reset races are eliminated in tests and hardware smoke | `.../reports/phase-01_REPORT_20-09-26.md` |
| 02 | [Device UI, manual color and Edit Zone](phase-02-ui-manual-zone_PLAN_20-09-26.md) | Device/zone/LED manual control and both JRAINBOW count dialogs work on real hardware | `.../reports/phase-02_REPORT_20-09-26.md` |
| 03 | [Modes, thermal ownership and profiles](phase-03-modes-thermal-profiles_PLAN_20-09-26.md) | Per-capability hardware effects, thermal/manual transitions and profile persistence work | `.../reports/phase-03_REPORT_20-09-26.md` |
| 04 | [Genuine vendor defaults](phase-04-vendor-defaults_PLAN_20-09-26.md) | Reset is enabled only for individually proven device paths and survives independent cold-boot validation | `.../reports/phase-04_REPORT_20-09-26.md` |
| 05 | [Release and system verification](phase-05-release-verification_PLAN_20-09-26.md) | Installed product works across restart, upgrade, sleep/reconnect and recovery, with explicit reset coverage | `.../reports/phase-05_REPORT_20-09-26.md` |

Phase 00 is read-only by default. Later phases require phase-entry re-research and separate execution approval. **Do not hand this entire program to one agent as one coding task.** In each phase: read selected plan and latest reports → inspect code drift → present findings → implementation approval → implement only selected scope → independent verification → overlapping regression checks → report evidence → logical code commit → process/context reconciliation → select next phase. `✅ VERIFIED` requires automated, integration, relevant real-hardware/manual, failure-path and user-confirmation evidence. `🔨 CODE DONE` never means finished. If no safe proof for a device's genuine reset exists, phase 04 remains partial/blocked and product requirement remains unmet for that device; other features may be delivered with transparent status.

## Cross-phase test matrix and release criteria

- Automated: existing Python `python -m unittest discover -s tests -v`; .NET `dotnet test sensor-bridge.Tests/OpenRGBTempSync.SensorBridge.Tests.csproj`; release verifier `powershell -File scripts/verify-release.ps1` (verify exact parameters at execution). Include new deterministic fake-SDK tests for duplicate names, rescan, identity ambiguity, mode flags, protocol mismatch, stale sensors, canceled writes, readback mismatch, save failure, and reset rejection. No hardware side effects in CI.
- Hardware: identify RAM A/B separately; RAM A red/RAM B blue; one selected LED only; both JRAINBOW count 0→N and N→M with readback and reopen; JRGB entire strip only; GPU manual and one supported effect; mainboard thermal while GPU remains hardware effect; sensor loss leaves manual/hardware unchanged; reset action never gets overwritten by pending thermal/off/profile writes.
- Lifecycle: clean launch and retry (UI responsive), rescan, app close/open, sleep/wake, engine crash/restart, Windows reboot, cold boot where defaults matter, one installer clean install/upgrade/repair/uninstall/rollback. Check port binding loopback only, owned child cleanup and no unconsented vendor software dependency.
- Evidence packet per phase: exact command/exit code, test count, installed/runtime version, source commit/lock hash, redacted logs, before/after state, screenshots, serial/topology mapping without sensitive dump, manual procedure and observed result. For factory reset also record vendor-tool/reference behavior **with app closed** and cold-boot outcome; a matching color alone is insufficient proof.
- Performance target to measure, not pre-claim: UI action feedback <250 ms except scan/resize with progress indication; no main-thread hardware/network wait; thermal loop remains bounded by existing 20 Hz nominal rate; no writes after stop/unmanage/reset completion.

## Acceptance Criteria

- Both RAM modules are independently selectable despite identical OpenRGB names; no wrong-device write.
- JRAINBOW1 and JRAINBOW2 can be resized separately, read back exactly, visibly light the connected devices and persist through app restart.
- A chosen individual LED/zone/device changes only the scope the hardware supports; unsupported controls have explicit reasons.
- Hardware effects, manual colors and thermal sync transition without race, stale-sensor fallback or UI freeze.
- App profile and device persistence actions remain distinct; no continuous flash writing.
- Manufacturer reset is correct for each device explicitly claimed supported, proven independently of a pre-sync snapshot and app profile; unsupported devices are not misrepresented.
- One installer and UI work across clean install, upgrade, restart, sleep/wake and rollback, with user-confirmed hardware behavior.

## Touchpoints

Python runtime `src/openrgb_temp_sync/`, entrypoint `src/openrgb_tray_app.py`, Python/.NET tests, build scripts, dependency locks, PyInstaller spec, installer and documentation. Exact allowed files are narrowed in each phase.

## Blast Radius

High: hardware write ordering, device identity, config migration, OEM reset and installer. Medium: UI framework and user profiles. Low: presentation. Preserve current thermal behavior and user config throughout.

## Verification Evidence

Each phase report records exact commands, exit codes, test count, device/readback state, redacted logs, screenshots and user-confirmed manual results. Final release needs cold-boot reset proof for every claimed device and installer rollback evidence.

## Blast radius, non-goals and safety

High risk: motherboard/DRAM controller writes, persistence, reset, process supervision and installer. Medium: UI dependency migration and profiles. Low: presentation. Do not modify OpenRGB firmware, motherboard BIOS/CMOS, RAM SPD, EEPROM raw bytes, or arbitrary MSI 185-byte packets. No remote OpenRGB server exposure, auto-update, audio/game integrations, every-brand support or software-simulated independent hardware effects unless later separately approved. No forced termination of MSI Center/other RGB tools; detect conflict and explain it. Back up config before migration; rollback uses previous installer + backed-up config, not a destructive git reset.

## Resume and execution handoff

First selected plan: `process/features/rgb-control/active/phase-00-capabilities-reset_PLAN_20-09-26.md` only. Before execution read `AGENTS.md`, this umbrella plan, that phase file, relevant `process/context/` routing, prior general plan, current `git status --short`, and current source. Do not assume old plan phase statuses reflect the present worktree. The user asked for a plan in this turn, **not implementation**. After phase 00 findings, pick exactly one next phase and obtain the required approval checkpoint.

## Implementation Checklist

- [ ] Verify current repository/dependency/hardware baseline without changing LED state.
- [ ] Record per-device zone/mode/save/reset capability and unknowns.
- [ ] Preserve config/dirty-worktree state before source edits.
- [ ] Build unique RAM/device identity and a single serialized command path.
- [ ] Protect thermal behavior with tests before replacing Tk UI.
- [ ] Implement device tree, zone/LED selection, manual colors and Edit Zone for both JRAINBOW headers.
- [ ] Implement capability-driven hardware modes, thermal ownership and profile transitions.
- [ ] Prove and implement vendor-default restoration separately for each target device; never relabel snapshot recovery.
- [ ] Run automated, hardware, lifecycle, installer and rollback matrices; obtain user visual confirmation.
- [ ] Keep phase reports and statuses honest; update old plan overlap and archive only after verification.

**Next Step:** Review this plan set, then select `phase-00-capabilities-reset_PLAN_20-09-26.md` as the only first execution anchor; no source implementation starts merely because the plan exists.
