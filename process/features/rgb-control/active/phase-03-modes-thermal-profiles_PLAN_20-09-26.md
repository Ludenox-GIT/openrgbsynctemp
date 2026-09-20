# Phase 03 — device effects, thermal ownership and app profiles

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (automated mode/thermal/profile contracts pass; live effect readback and user confirmation remain pending). **Depends on:** Phase 02 verified. **Report:** `process/features/rgb-control/reports/phase-03_REPORT_20-09-26.md`.

## Overview

Add capability-driven hardware modes, retain thermal mapping and persist user profiles. Read `process/context/all-context.md`; `process/context/tests/all-tests.md` is stale for this RGB project.

## Phase Completion Rules

`✅ VERIFIED` requires integration tests, real-device modes, config readback, error tests, thermal regression and User Confirmation; source-only is `🔨 CODE DONE`.

## Objective / green check

Every detected device exposes only the modes and parameters its OpenRGB controller supports. Temperature sync is selectable per target and coexists with manual/hardware modes on other devices. App profiles persist assignments without accidental device-flash writes.

## Touchpoints / public contracts

`openrgb_runtime.py` mode descriptors and exact SDK mode parameter adapter; `controller.py` owner transitions; `lighting.py` existing thermal curve/EMA/interpolation; `sensor_runtime.py` health; `config.py` versioned profiles; PySide6 UI mode and temperature panels. Tests: extend `test_openrgb_runtime.py`, `test_controller.py`, `test_config.py`, `test_lighting.py`, add focused UI-model test. Protocol 4 missing flags are a version-gated unsupported state, not guessed controls or unchecked protocol bump.

Hardware mode parameters are validated from live flags (`colors`, `speed`, `direction`, `brightness`, `manual_save`, `automatic_save`). `Save profile` writes app config; `Save to Device` calls a supported mode-specific SDK operation only after explicit user action and readback/confirmation. Never flash on each thermal frame. Native hardware effects may be device-wide; different zone effects are offered only where exact controller supports them. Manual + thermal can compose per LED only in Direct mode and only where addressable LED mapping supports it; otherwise prevent contradictory assignments with a clear scope message.

## Implementation Checklist and tests

- [ ] Write failing capability tests for MSI, ENE, GPU mock mode lists: unsupported speed/direction/brightness hidden, save capabilities mode-specific, Direct per-LED only if advertised.
- [ ] Implement normalized mode descriptors/version gate; test SDK protocol mismatch and partial mode data without crashing.
- [ ] Implement hardware-mode transitions through dispatcher; test pending thermal writes canceled, readback mismatch surfaced, no background Direct re-entry while effect is active.
- [ ] Integrate thermal panel with live CPU/GPU freshness and per-target assignment; test CPU missing does not block GPU-only thermal and GPU missing is not silently mapped to CPU.
- [ ] Add app profiles/config migration and readback. Test independent RAM profiles and zone counts, unknown device retained, profile load does not override unmanaged or just-reset devices without explicit apply.
- [ ] Implement conditional Save to Device with deliberate confirmation and no recurring flash writes; test unsupported and write-failure result.
- [ ] Run Python and .NET tests; hardware: GPU hardware effect while MSI JRAINBOW thermal and RAM manual; change modes repeatedly; loss/recovery of sensor and OpenRGB connection; app restart/profile reload.

## Failure / rollback / green boundary

If a mode exists but exact parameter mapping is not exposed via current SDK, mark that parameter unavailable and research protocol upgrade. Do not emulate an unsupported effect unless separately approved. Green requires current temperature sync regression pass, correct independent assignments and user-observed physical mode changes. No claim of manufacturer reset.

## Public Contracts

Capability flags govern every effect control and Save to Device state; assignments use stable device keys and exactly one owner per device.

## Blast Radius

Mode writes, thermal scheduling, sensor failure behavior and profile persistence; do not modify vendor reset handling here.

## Acceptance Criteria

Each mode exposes only supported controls; manual/hardware/thermal ownership transitions without cross-write; profiles reload correct targets; sensor loss affects thermal only; save-to-device is explicit and capability gated.

## Verification Evidence

Record Python/.NET test output, per-device mode observations, profile reload/readback, sensor-loss case, firmware-save gating and user confirmation in the phase report.

## Agent handoff

One controller/mode coding worker, separate test review. Read Phase 00 capability matrix and Phase 01–02 reports first. Next: `phase-04-vendor-defaults_PLAN_20-09-26.md`.

## Resume and Execution Handoff

Primary execute anchor: this exact file. Supporting phase files: umbrella plan and Phase 00–02 reports; retain earlier verified behavior.

**Next Step:** Execute this phase only after Phase 02 verified and fresh phase-entry research/approval.
