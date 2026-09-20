# Phase 00 — capability and reset feasibility

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🧪 TESTING (read-only capability matrix and reset feasibility recorded; exact-device proof remains pending). **Type:** read-only research first. **Depends on:** umbrella plan. **Report:** `process/features/rgb-control/reports/phase-00_REPORT_20-09-26.md`.

## Overview

Read-only capability and reset feasibility gate for the unified RGB product. Read `process/context/all-context.md`; `process/context/tests/all-tests.md` describes a stale Newton simulator and must not override this RGB plan.

## Phase Completion Rules

`✅ VERIFIED` requires source/integration evidence, explicit unknowns, manual user review and User Confirmation of the findings; no device-control claim is made. Code existence is only `🔨 CODE DONE`.

## Objective / green check

Record actual machine and source capabilities and a device-by-device factory-default proof strategy. Green proves the matrix is accurate and unknowns are explicit; **it does not prove reset works**. This is the only phase selectable first.

## Touchpoints and research instructions

- Read `src/openrgb_tray_app.py`, `src/openrgb_temp_sync/{openrgb_runtime,controller,config,ui,sensor_runtime,lighting}.py`, `requirements.lock`, `third_party/dependencies.lock.json`, `tests/`, installer/build scripts and prior plan/report. Capture `git status --short` without changing files.
- Inspect the pinned OpenRGB source for `RGBController` mode flags, ZoneEditor size rules, `MSIMotherboard185Controller` and RGB controller, ENE SMBus and Gigabyte RGB Fusion GPU. Record the exact bundled binary version and current SDK protocol negotiation, not just upstream master behavior.
- With user consent at execution time, use controlled *read-only* SDK enumeration of device metadata/zone names/count/ranges/flags/modes/saving, and photograph the current physical lights. Do not call APIs that implicitly force Direct mode. The current `_connect_client` does force Direct, so do not use it for read-only enumeration unchanged.
- Read official MSI Mystic Light SDK/manual and exact-board documentation, official G.SKILL reset/cold-boot description, and Gigabyte model-specific information. Treat MSI proprietary behavior absent from public documentation as unknown, not a guessed API. Research `Default` vs app profile vs hardware effect vs EEPROM reset.
- For each target (RAM A, RAM B, GPU, motherboard zones), mark `verified / unverified / unsupported` for genuine reset and state what proof would change status. Identify device/firmware versions and software used for comparison. No raw HID/SMBus packet exploration on the user's PC under this phase.

## Implementation Checklist

- [ ] Save read-only baseline: git diff inventory, dependency versions/hashes, device model/firmware where exposed, Windows state, current zone counts/modes, connection topology stated by user (both JRAINBOW headers connected).
- [ ] Produce source-to-capability table: device → zones → resizable/max/min → LED addressing → modes and parameter flags → save semantics.
- [ ] Confirm what protocol 4/openrgb-python 0.3.7 actually exposes; write compatibility decision for capabilities it omits (adapter, compatible upgrade, or feature-gate) without implementing yet.
- [ ] Research reset for MSI, ENE/G.SKILL, Gigabyte separately; write exact evidence and blocking unknowns. For G.SKILL, distinguish software Reset settings from cold-boot rainbow behavior.
- [ ] Define reproducible, non-destructive acceptance scenario per device: deliberately select non-default, close app/other controllers, restore by verified path, inspect before Windows/after cold boot and after reconnect, compare to documented/default behavior. **Do not execute this scenario yet.**
- [ ] Present findings and explicit next-action/permission checkpoint before Phase 01 source changes.

## Tests / verification evidence

Read-only source/installed-version comparisons and capability table with links/file lines. No unit test or device write required. Report exact commands, SDK read semantics, firmware unknowns, and screenshots. If read-only SDK cannot be guaranteed, use cached OpenRGB UI/source evidence and mark hardware enumeration unverified.

## Acceptance Criteria

The exact per-device capability/reset matrix, protocol compatibility decision and reproducible proof scenarios exist in the phase report, with unknowns not mislabeled as supported.

## Verification Evidence

The report contains links/lines, versions, commands, screenshots and user review; no hardware writes or config changes.

## Public contracts / blast radius / blockers

No source or config mutation. Output is the evidence matrix consumed by later phases. If target hardware identity cannot be separated, identify that as Phase 01 blocker; do not silently bind two `ENE DRAM` devices. If reset cannot be proven now, Phase 01–03 may proceed with reset disabled, but Phase 04/full product cannot be marked complete.

## Blast Radius

Read-only source/device inventory only; avoid the current connection helper because it changes Direct mode.

## Resume and Execution Handoff

Primary execute anchor: this exact file. Supporting phase files: umbrella program plan; no other phase may be implemented under this anchor.

## Agent handoff

Assign a research agent this file and umbrella only; require read-only operations and a report. Next executable phase after accepted findings: `phase-01-identity-serial-core_PLAN_20-09-26.md`.

**Next Step:** Begin this phase's read-only research only after selecting this exact plan file.
