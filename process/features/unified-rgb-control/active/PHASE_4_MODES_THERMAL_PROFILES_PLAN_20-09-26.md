# Phase 4 — Hardware Effects, Thermal Mode, and App Profiles

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phase 3 `✅ VERIFIED`  
**Report:** `process/features/unified-rgb-control/reports/phase-4-modes-profiles_REPORT_20-09-26.md`

## Objective

Make Manual, Hardware Effect, and Temperature first-class mutually exclusive ownership modes. Render only controller-reported parameters, preserve the current thermal mapping, and add app profiles without confusing them with persistence inside a controller.

## Touchpoints

Modify: `controller.py`, `device_model.py`, `command_dispatcher.py`, `openrgb_runtime.py`, `lighting.py`, `config.py`, `desktop_ui.py`, tray entrypoint/menu, and tests. Add `profiles.py` only if profile validation/activation cannot remain cleanly in `config.py`.

## Public Contracts

- Ownership transition is atomic: barrier → stop old producer → generation increment → set required mode → apply settings → start new producer → result.
- Hardware-effect controls derive from mode flags/ranges. Missing capabilities are hidden/disabled with reason.
- Profile stores desired app state keyed by stable ids and may contain partial targets. Activation reports applied, skipped, unresolved, and failed targets.
- Device save is a separate confirmed command and is unavailable during thermal ownership.

## Implementation Checklist

- [ ] Add transition-table tests covering every valid/invalid pair among `UNMANAGED`, `MANUAL`, `HARDWARE_EFFECT`, `THERMAL`, `BLACKOUT`, and maintenance/reset states.
- [ ] Normalize mode names/ids and flags from Phase 0; retain raw metadata for diagnostics.
- [ ] Implement Manual ownership using Direct/per-LED where supported and safe whole-scope fallback where not.
- [ ] Implement Hardware Effect ownership with reported color cardinality, speed, brightness, direction, and random/mode-specific/per-LED choices; never present parameters absent from flags.
- [ ] State controller-wide scope explicitly when one hardware mode controls every motherboard zone.
- [ ] Move current EMA/interpolation/CPU-GPU source behavior into Thermal ownership without changing math; stale/missing CPU affects only CPU-bound targets and never silently falls back to GPU or old readings.
- [ ] Rate-limit/coalesce thermal frames while preserving mode barriers and UI responsiveness.
- [ ] Implement app profile create/rename/duplicate/delete/apply/export/import with schema validation, stable ids, aliases for display, and unresolved-target review.
- [ ] Keep Save App Profile and Save to Device separate. Device-save requires capability, confirmation, structured result, and no repeated flash writes.
- [ ] Define startup policy: restore chosen app profile only when explicitly enabled; factory-reset/relinquished devices are excluded until user opts in again.
- [ ] Update tray actions to reflect ownership accurately; “Stop Sync” stops thermal producer, not manual/hardware ownership unless wording says so.
- [ ] Add reconnect/sleep recovery: rediscover, reconcile ids, restore ownership only after capability check, and reject stale pre-disconnect frames.
- [ ] Test mixed scenario: motherboard thermal while GPU runs a supported hardware effect and two RAM sticks have distinct manual colors.

## Test Matrix

- Unit: capability rendering, mode settings validation, transitions, thermal stale data, profile serialization/migration, unresolved targets, flash-save gating.
- Concurrency: rapid tab/mode changes, profile activation during thermal frames, blackout during mode change, disconnect during activation, retry after failure.
- Performance: 30-minute 20 Hz thermal run; record command rate, coalescing, queue depth, CPU, memory, UI latency, and errors. Acceptance targets are no unbounded growth, no overlapping writes, and p95 UI action acknowledgement under 250 ms excluding hardware latency.
- Manual target matrix: representative mode for MSI mainboard, each RAM, and GPU; unsupported controls hidden; restart/profile behavior; mixed ownership scenario.
- Regression: zone counts unchanged, duplicate RAM independent, installer/runtime lifecycle intact.

## Error Semantics

Partial profile activation is never “success” without a summary. A failed mode transition leaves the controller `Degraded/Unmanaged`, stops producer writes, and offers retry. Missing sensor shows stale/unavailable state; last temperature is not used indefinitely.

## Rollback

Profiles are additive and exportable. Keep prior config backup. Reinstall prior build to recover baseline thermal-only behavior; do not auto-apply profiles during rollback.

## Blast Radius

All normal lighting behavior and ongoing command volume. Risks include race conditions, incorrect mode scope, flash wear, and profile misapplication; barriers, flags, stable ids, and explicit saves mitigate them.

## Verification Evidence

Transition tests, performance log, profile round-trip files, per-device capability screenshots, mixed-mode photos/video, disconnect/sleep results, and user confirmation.

## Resume and Execution Handoff

Assign one execute agent and separate tester/race reviewer. Begin with current Phase 1–3 reports and fresh mode enumeration. Do not implement manufacturer reset here.
