# Phase 1 — Stable Identity, State Ownership, and Single-Writer Foundation

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phase 0 report accepted  
**Report:** `process/features/unified-rgb-control/reports/phase-1-foundation_REPORT_20-09-26.md`

## Objective

Remove the correctness defects that make expanded control unsafe: duplicate device-name keys, direct writes from multiple paths, non-atomic reset/thermal transitions, stale device lists, and fragile v2 configuration. Preserve existing thermal behavior while introducing identity, capability, ownership, command, and migration contracts.

## Phase Completion Rules

The phase is verified only after automated tests, a live read-only inventory, controlled manual color writes approved by the user, state-file inspection, error tests, regression tests, and user confirmation.

## Touchpoints

Modify: `src/openrgb_temp_sync/openrgb_runtime.py`, `controller.py`, `config.py`, `src/openrgb_tray_app.py`.  
Add minimally: `src/openrgb_temp_sync/device_model.py`, `src/openrgb_temp_sync/command_dispatcher.py`.  
Tests: `tests/test_openrgb_runtime.py`, `test_controller.py`, `test_config.py`; add `tests/test_device_model.py`, `tests/test_command_dispatcher.py` only because these are new behavioral units.  
Do not change UI layout in this phase beyond adapting existing calls to ids.

## Public Contracts

- Immutable `DeviceSnapshot`, `ZoneSnapshot`, `LedSnapshot`, and capability records as specified by the umbrella.
- Opaque `DeviceId` with an identity migration report; duplicate display names receive distinct ids.
- Per-device ownership state and monotonically increasing generation.
- Command/result envelope and barrier/coalescing semantics.
- Config schema v3 with unresolved legacy entries preserved.

## Code Guidance

Pseudocode sequence for all writes:

```text
submit(command)
  validate target exists and expected generation matches
  enqueue; coalesce only eligible color frames
dispatcher worker
  acquire sole adapter access
  if barrier: drain/reject stale frames
  perform transition/write/readback
  publish typed result and refreshed snapshot
```

Keep OpenRGB SDK objects private to the runtime/adapter thread. UI and controller consume snapshots, never retain mutable SDK device objects. Refresh discovery atomically after reconnect/resize. The dispatcher owns mode transition ordering: pause previous owner → increment generation → set required mode → apply values → publish state.

## Implementation Checklist

- [ ] Add characterization tests reproducing duplicate `ENE DRAM` overwrite/first-match behavior, late thermal write after restore, resume without Direct mode, blackout/held-device inconsistency, stale inventory, and ambiguous v2 migration.
- [ ] Implement snapshot normalization and deterministic identity from Phase 0 fields; test stable ordering across discovery reorder and distinct duplicate-name ids.
- [ ] Replace `_device_baselines`, holds, caches, config lookups, and UI-facing selection inputs that currently key by display name with ids; keep names as labels/legacy aliases.
- [ ] Implement a single dispatcher worker with typed results, generation rejection, barrier commands, bounded queue, thermal coalescing, stop/drain semantics, and structured logging.
- [ ] Route Direct-mode setup, color writes, blackout, restore-snapshot compatibility action, resume, zone resize, retry/reconnect, stop, and device-save requests through the dispatcher.
- [ ] Rename the existing pre-sync behavior in contracts/logs to `Restore session snapshot`; remove all `factory`, `original`, or vendor-default implications.
- [ ] Ensure resume explicitly enters the required mode before accepting thermal frames.
- [ ] Ensure blackout records prior ownership without violating a reset/maintenance hold, and lights-on restores ownership through a barrier.
- [ ] Make inventory replacement atomic and trigger snapshot publication after reconnect/resize.
- [ ] Implement config v2→v3 migration with backup, deterministic matches, unresolved duplicate-name records, alias retention, and atomic save; never assign one legacy profile to both RAM sticks silently.
- [ ] Add fault tests for disconnect during barrier, SDK exception, dispatcher shutdown, stale generation, queue saturation, unsupported mode, missing identity fields, and corrupt migration input.
- [ ] Run targeted tests, full Python suite, and a five-minute dispatcher soak with a mock adapter; assert one concurrent adapter call maximum and bounded queue/memory.
- [ ] With user approval, run the live distinction check: address RAM A then RAM B using ids and confirm independent results; restore by the session-snapshot compatibility action only, clearly labelled non-factory.

## Test Commands and Pass Criteria

- `python -m unittest tests.test_device_model tests.test_command_dispatcher tests.test_openrgb_runtime tests.test_controller tests.test_config -v` — zero failures.
- `python -m unittest discover -s tests -p "test_*.py" -v` — zero regressions.
- Existing release/dependency checks remain green if their inputs changed.
- Soak evidence shows no overlapping adapter calls, no unbounded queue growth, and stale frames rejected after a barrier.

## Rollback

Keep v2 backup and a reader fallback for one release. If live identity mapping is ambiguous, stop writes and leave the record unresolved. Roll back by reinstalling the previous build and restoring the v2 backup; never downgrade a v3 file in place.

## Blast Radius

All device writes and configuration lookup paths. Main risks are deadlock, lost frames, and incorrect migration. Mitigate with bounded waits, deterministic teardown, characterization tests, and no UI rewrite in the same phase.

## Verification Evidence

Test logs, migration before/after diff with secrets removed, dispatcher concurrency metrics, distinct RAM id snapshot, live A/B result, error-state screenshots/logs, and regression list.

## Resume and Execution Handoff

Fresh research must compare current code/diff with this plan and Phase 0 identity fields. Execute only this phase. Do not start PySide6 UI or vendor reset. Green proves the foundation is safe enough for UI work, not that reset or JRAINBOW works.
