# Phase 01 — stable identity and serialized control core

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (automated contracts pass; live hardware and user confirmation remain pending). **Depends on:** Phase 00 matrix and execution approval. **Report:** `process/features/rgb-control/reports/phase-01_REPORT_20-09-26.md`.

## Overview

Stabilize device targeting and hardware write order. Read `process/context/all-context.md` and interpret stale `process/context/tests/all-tests.md` using the RGB-specific test commands below.

## Phase Completion Rules

`✅ VERIFIED` requires integration, manual hardware, config/readback, failure-path and User Confirmation evidence, plus relevant regression checks; code-only is `🔨 CODE DONE`.

## Objective / green check

Protect current thermal behavior while ensuring every command targets a unique device and no two hardware writes race. Green proves RAM A/B isolation and serialized mode/state transitions, not new UI or vendor reset.

## Touchpoints

`src/openrgb_temp_sync/openrgb_runtime.py` (fresh inventory, lookup, capability adapter, write results), `controller.py` (owner state and command dispatcher), `config.py` (versioned migration), `lighting.py` (reuse unchanged math), `ui.py` only to keep old UI operable, `src/openrgb_tray_app.py` lifecycle; tests `test_openrgb_runtime.py`, `test_controller.py`, `test_config.py` plus a new focused dispatcher test if needed.

## Public contracts and code guidance

- Build normalized `DeviceDescriptor/ZoneDescriptor/ModeDescriptor` values at SDK boundary. Enumerate metadata (type, vendor/product IDs, serial/location/path if present, zone shape); persist a stable key only when evidence supports it. Keep session index separately and refresh it after rescan. On ambiguous identical RAM, require guided explicit mapping and prohibit ambiguous writes; never use `device.name` as dictionary key or return first match.
- Queue typed commands (`set_owner`, `set_colors`, `set_mode`, `resize_zone`, `save_to_device`, `lights_off`, `stop`, `rescan`) through one worker. Have it own the SDK client and device objects. Each command resolves current target key and inventory generation, validates capabilities and records requested/readback result. Thermal loop produces desired frames, not direct SDK calls. Coalesce superseded thermal frames; never coalesce reset, resize or mode transitions.
- Owner state per device: unmanaged/manual_direct/hardware_mode/thermal_direct/resetting. On transition: reject stale target, pause prior frames, negotiate mode, apply state, verify, release queued updates. Resume thermal must explicitly negotiate Direct. Stop/unmanage must guarantee no later queued writes. Screensaver/off overlay must not permanently alter held/unmanaged/reset state.
- Migrate existing name-keyed config with backup + atomic write. Unique names may map automatically only if metadata confirms; the duplicate `ENE DRAM` setting remains unresolved until explicit binding. Preserve both old entries and backups for rollback. Never apply one ambiguous profile to both RAMs.
- Rename pre-sync restore to `restore_pre_sync_snapshot` (or equivalent) in code/UI and tests; do not call it factory reset. Remove premature Direct-mode switch during read-only enumeration. Preserve existing thermal curve semantics, process supervision and tray startup.

## Implementation Checklist and tests

- [ ] Capture pre-edit config SHA-256, backup and current test baseline; review dirty diff.
- [ ] Add failing tests: two same-name mock RAMs retain separate identity/baseline; ambiguous mapping rejects writes; reconnect changes SDK indices but not target key.
- [ ] Implement descriptor/identity resolution at `openrgb_runtime.py`; add readback and structured errors; test inventory replacement and zone resize mismatch.
- [ ] Add failing concurrency tests: pending thermal frame cannot overwrite mode change/restore/resize; lights-off overlay respects unmanaged/held devices; stop drains/invalidates queued work.
- [ ] Implement single writer and owner transitions in `controller.py`; ensure resume sets Direct; explicit stale sensor behavior affects thermal owner only.
- [ ] Add config migration and rollback tests, including duplicate-name unresolved state, unknown fields and save failure; implement migration.
- [ ] Update old Tk UI calls minimally for new IDs; show a clear error when identity is ambiguous; do not redesign UI in this phase.
- [ ] Run `python -m unittest discover -s tests -v`; record count/exit code. On real hardware, test RAM A/B unique targeting with bounded single-color commands after user authorizes writes; verify no cross-write and thermal regression.

## Failure / rollback / blast radius

High: wrong-device writes and configuration loss. Abort on ambiguous/stale identity; preserve legacy config and previous installer. SDK disconnect transitions owners to degraded, not to a new random device. No firmware/save-to-device writes during this phase. Green requires automated race/identity tests, manual RAM isolation, current temperature flow, and user confirmation.

## Blast Radius

Hardware targeting, queue lifecycle and config migration are high risk; restrict phase changes to the listed runtime/tests and preserve pre-edit backups.

## Acceptance Criteria

Both same-name RAM devices are independently addressed; ambiguous identity rejects writes; all SDK writes are serialized; reset/resize/thermal do not race; config migration is reversible; existing thermal flow remains intact.

## Verification Evidence

Record pre/post config hashes, exact Python test output, wrong-device and race test results, real RAM isolation observation, temperature regression and user confirmation in the phase report.

## Agent handoff

One coding agent owns this phase; an independent reviewer verifies real diff and tests. Re-research phase entry and use this exact plan only. Then report, regression-check earlier runtime and hand off `phase-02-ui-manual-zone_PLAN_20-09-26.md`.

## Resume and Execution Handoff

Primary execute anchor: this exact file. Supporting phase files: umbrella program plan and Phase 00 research report. Read current diff and preserve user changes.

**Next Step:** Enter execution for this phase only after Phase 00 is accepted and implementation approval is recorded.
