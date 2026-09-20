# Unified RGB Control — Phase Program

**Date:** 20-09-26  
**Complexity:** COMPLEX — six dependent implementation phases plus one research gate  
**Status:** ⏳ PLANNED  
**Primary execute anchor:** `process/features/unified-rgb-control/active/PHASE_0_RESET_CAPABILITY_RESEARCH_PLAN_20-09-26.md`

## Overview

Evolve the installed OpenRGB Temp Sync utility into one honest, device-aware RGB controller. The UI follows the useful OpenRGB hierarchy — device → zone → LED — while retaining temperature synchronization as one selectable lighting mode. The product adds manual color control, supported hardware effects, independent JRAINBOW1/JRAINBOW2 LED-count editing, app profiles, and manufacturer-default restore only where a vendor-specific procedure has been proven on the exact controller.

This program extends, but does not silently replace, `process/general-plans/active/unified_rgb_desktop_app_PLAN_19-09-26.md`. That predecessor remains the source for the bundled engine, sensor bridge, Windows lifecycle, and installer baseline. No executor may run both plans concurrently. The legacy `rgb_brightness_config_PLAN_31-05-26.md` is historical input only.

## Quick Links

- [Goals and non-goals](#goals-and-non-goals)
- [Architecture](#architecture-decisions)
- [Data and state contracts](#public-contracts)
- [Phase order](#phase-order-and-proof-boundaries)
- [Agent handoff](#agent-handoff-contract)
- [Complete checklist](#program-checklist)

## Phase Completion Rules

A phase is not complete until all five conditions hold:

1. **Integration test:** the phase works with the installed app, bundled OpenRGB process, sensor bridge, and existing configuration path.
2. **Manual test:** the user can perform the affected workflow on the target PC.
3. **State verification:** configuration, device state, logs, and readback evidence match the expected result.
4. **Error handling:** defined failure and unsupported cases are visible, safe, and non-destructive.
5. **User confirmation:** the user explicitly confirms the observed behavior.

Status meanings: `⏳ PLANNED`, `🔨 CODE DONE`, `🧪 TESTING`, `✅ VERIFIED`, `🚧 BLOCKED`.

Build success, mocks, screenshots, or one successful write never qualify a phase as verified. Each phase writes a durable report under `process/features/unified-rgb-control/reports/` and reruns the narrowest regression checks for all earlier verified phases.

## Goals and Non-Goals

### Goals

- Present every detected RGB controller once with stable identity even when display names collide.
- Navigate device → zone → LED and select one, many, a whole zone, a device, or selected devices.
- Apply static/manual colors at the finest granularity the controller actually supports.
- Expose only hardware modes and parameters reported by the controller.
- Keep temperature mapping, EMA, interpolation, CPU/GPU sources, per-LED brightness, tray lifecycle, and diagnostics.
- Configure JRAINBOW1 and JRAINBOW2 independently with user-entered counts and readback.
- Save app profiles separately from device-flash persistence.
- Restore genuine manufacturer defaults only after exact-device proof; otherwise show `Not supported` or `Research required`.
- Ship one installer and preserve existing user configuration with recoverable migration.

### Non-goals

- Reimplement OpenRGB device drivers or fork the OpenRGB GUI.
- Promise every OpenRGB-supported device works before it enters the hardware matrix.
- Treat an OpenRGB software limit as an electrical power rating.
- Auto-discover the physical number of ARGB LEDs where hardware exposes no such query.
- Run different native hardware effects per zone when the controller supports only controller-wide mode selection.
- Capture or replay undocumented vendor packets on user hardware without an approved, reversible lab procedure.
- Clear CMOS, erase controller flash, change firmware, or run unsafe bus scanning.
- Call `Rainbow`, `Default` style, pre-sync snapshot restore, Direct-mode exit, or profile deletion a factory reset.
- Touch the unrelated Newton simulator.

## Architecture Decisions

1. **Reuse the bundled OpenRGB engine and current sensor bridge.** Do not create RGB drivers or a second monitoring stack.
2. **Replace the fixed Tk settings view with PySide6, not Electron.** One native dependency is sufficient for a scalable tree, selection model, worker signals, dialogs, and accessibility. The tray/runtime remains Python.
3. **Introduce one serialized command dispatcher.** UI, thermal loop, profile activation, blackout, zone resize, and reset submit commands; none writes hardware directly.
4. **Use capability-driven UI.** Controls are derived from immutable discovery snapshots, not hard-coded device-name checks.
5. **Use stable logical identity.** Never key configuration or runtime holds by display name. Identity uses the strongest available controller fields plus a deterministic collision ordinal, while preserving aliases separately.
6. **Treat lighting ownership as explicit state.** `UNMANAGED`, `MANUAL`, `HARDWARE_EFFECT`, `THERMAL`, `BLACKOUT`, and `RESETTING` are mutually exclusive per controller. Zone/LED selections are targets, not owners.
7. **Keep factory reset outside normal modes.** It is a maintenance command with per-family evidence and post-reset relinquish semantics.
8. **Separate app profile save from device save.** Device flash writes are opt-in, capability-gated, confirmed, rate-limited, and never used by the 20 Hz thermal path.
9. **Protocol compatibility is negotiated.** The current `openrgb-python==0.3.7`/protocol-4 client is not “upgraded” by changing a constant. Phase 0 must prove whether required metadata is available or select a tested compatible client change.

## High-Level Data Flow

```text
OpenRGB discovery -> immutable DeviceSnapshot/Capabilities -> UI model
UI / thermal worker / tray / profiles -> LightingCommand queue
LightingCommand queue -> single CommandDispatcher -> OpenRGB adapter -> device
                                               |-> readback/result -> state store -> UI/log

Factory reset request -> reset capability registry -> confirmation -> exclusive reset command
 -> vendor-proven procedure -> relinquish ownership -> cold-boot/manual evidence
```

## Public Contracts

### Stable identity

`DeviceId` is an opaque persisted string produced by an identity builder. Inputs, in priority order, are stable OpenRGB/controller identity fields, vendor/type/location/serial where available, then a deterministic collision ordinal derived from a sorted discovery fingerprint. Display name and discovery list index are never sufficient alone. A migration table records old name keys and unresolved matches; ambiguous mappings stay unresolved and are shown to the user.

`ZoneId = DeviceId + stable zone signature`; `LedId = ZoneId + logical LED index`. Zone names are labels, not keys.

### Capability snapshot

Each device snapshot contains controller type, zones, LED ranges, current zone count, supported modes, per-mode flags, color cardinality, speed/brightness bounds, directions, save support, and reset-support status. Missing values are `unknown`, not invented defaults.

### Command envelope

Every command carries a unique id, target ids, expected ownership generation, operation, parameters, source (`ui`, `thermal`, `profile`, `tray`, `reset`), and completion result. Dispatcher rules:

- one hardware write sequence at a time;
- stale generation commands are rejected;
- reset/zone-resize/mode-change are barriers;
- frequent thermal color commands may coalesce only within the same target and generation;
- no coalescing for reset, save-to-device, resize, or profile transitions;
- readback or a documented lack of readback is recorded before success.

### Error and support semantics

Results are one of `APPLIED`, `REJECTED_STALE`, `UNSUPPORTED`, `REQUIRES_CONFIRMATION`, `FAILED_RETRYABLE`, or `FAILED_FATAL`. UI never turns `UNSUPPORTED` into success. Reset support is `RESEARCH_REQUIRED`, `SUPPORTED_UNVERIFIED`, `SUPPORTED_VERIFIED`, or `UNSUPPORTED`; only `SUPPORTED_VERIFIED` enables the production reset button.

### Configuration v3

The v3 document contains `schema_version`, device records keyed by `DeviceId`, aliases, zone counts keyed by `ZoneId`, active ownership/mode preferences, app profiles, unresolved legacy profiles, and migration metadata. Save remains atomic. The v2 file and a timestamped backup remain recoverable until v3 has loaded and saved successfully twice.

## UI Contract

```text
┌ Devices / Profiles ─────┬ Device workspace ──────────────────┬ Properties ─────┐
│ RAM A                    │ Device > Zone > LED selection      │ Color wheel     │
│ RAM B                    │ [Manual] [Effect] [Temperature]    │ RGB / HSV / Hex │
│ RTX 3060                 │ Zone: JRAINBOW1   [Edit zone…]     │ mode parameters │
│ MSI B550                 │ LED tiles / multi-select           │ Apply scope     │
│  ├ JRGB1                 │ capability and ownership status    │                 │
│  ├ JRAINBOW1             │                                    │                 │
│  └ JRAINBOW2             │                                    │                 │
├ Profiles ────────────────┴────────────────────────────────────┴─────────────────┤
│ Apply selection | Save app profile | Save to device* | Device maintenance…    │
└─────────────────────────────────────────────────────────────────────────────────┘
* visible only when supported; never used for thermal animation
```

Selection is staged until Apply unless live preview is explicitly enabled. `Cancel` restores the last confirmed UI state without a hardware write. Device maintenance contains `Stop managing` and, separately, verified `Restore manufacturer defaults`.

## Phase Order and Proof Boundaries

| Phase | Plan | Depends on | Green proves |
|---|---|---|---|
| 0 | `PHASE_0_RESET_CAPABILITY_RESEARCH_PLAN_20-09-26.md` | predecessor runtime available | Exact capabilities and honest reset feasibility are documented; protocol/dependency choice is locked. |
| 1 | `PHASE_1_FOUNDATION_STATE_COMMANDS_PLAN_20-09-26.md` | Phase 0 | Duplicate devices are distinct; all writes are serialized; v2 migrates safely. |
| 2 | `PHASE_2_PYSIDE_DEVICE_ZONE_LED_UI_PLAN_20-09-26.md` | Phase 1 | New UI can browse and manually color supported scopes without thermal races. |
| 3 | `PHASE_3_JRAINBOW_ZONE_CONFIGURATION_PLAN_20-09-26.md` | Phase 2 | Both JRAINBOW ports accept independent user counts with readback and persistence. |
| 4 | `PHASE_4_MODES_THERMAL_PROFILES_PLAN_20-09-26.md` | Phase 3 | Hardware effects, thermal mode, app profiles, and ownership transitions coexist safely. |
| 5 | `PHASE_5_VENDOR_DEFAULT_RESET_PLAN_20-09-26.md` | Phase 0 evidence + Phase 4 | Verified families restore manufacturer state and app relinquishes control; unsupported families remain honest. |
| 6 | `PHASE_6_RELEASE_HARDWARE_VALIDATION_PLAN_20-09-26.md` | Phases 1–5 | Installer, upgrades, sleep/reboot/cold boot, performance, and the full target hardware matrix pass. |

Only one phase plan is handed to EXECUTE at a time. Every later phase begins with fresh read-only research against the selected plan, upstream reports, current diff, and target hardware state.

## Dependency and Build Impact

- Candidate runtime dependency: PySide6, pinned in `requirements.in` and lock regenerated only in Phase 2 after packaging proof. Remove Tk-specific runtime imports once cutover is accepted; do not maintain two production UIs.
- Keep Pillow/pystray/OpenRGB/psutil/pywin32 unless measurements prove removal safe.
- `scripts/build-app.ps1`, `scripts/build-installer.ps1`, `scripts/verify-release.ps1`, and `installer/OpenRGBTempSync.iss` must include Qt plugins deterministically and verify absence of accidental Qt modules.
- OpenRGB client/package changes are blocked until Phase 0 compatibility tests pass against the pinned OpenRGB engine.
- Config migration must not overwrite unknown user keys or unresolved duplicate-name records.

## Cross-Cutting Safety and Rollback

- Before each hardware phase, export current app config, OpenRGB profile/config, exact device inventory, and app/OpenRGB versions.
- Never run MSI Center, RGB Fusion/GCC, G.SKILL control, and the app as concurrent owners during writes.
- JRAINBOW1/2 LED counts are logical mapping values. Driver maxima (for the reviewed board, 200/240) are not electrical capacity. Do not advise connecting more load or changing wiring. Preserve the board manual's 5 V ARGB polarity and power limits.
- Each phase must remain revertible by restoring the previous installer and v2 config backup. No phase deletes a profile or writes device flash automatically.
- If a dispatcher transition fails, stop writes for that controller and expose `Degraded`; do not continue with assumed state.
- Factory reset research never runs undocumented destructive commands on the user's only hardware. If proof needs packet capture, use official software, read-only comparison first, explicit user approval, and a recovery path.

## Agent Handoff Contract

For every phase, the orchestrator sends one exact phase path and this umbrella as support. Suggested prompt shape:

> Work only from `<selected phase path>` with supporting context `<umbrella path>` and the latest upstream reports. Begin with read-only pre-phase research and stop with findings. Do not implement until the user explicitly enters EXECUTE for this exact phase. Preserve unrelated and user-authored changes. During execution, modify only listed touchpoints unless a blocker is reported. Run automated tests, then request the documented manual hardware checks. Record evidence in the phase report path. Never mark hardware behavior verified from mocks.

Roles by phase:

- Phase 0: research agent; no code or device writes.
- Phase 1: execute agent, then tester and correctness reviewer.
- Phase 2: UI/UX execute specialist, tester, accessibility/manual reviewer.
- Phase 3: execute agent plus hardware-test operator; one writer only.
- Phase 4: execute agent, tester, race/concurrency reviewer.
- Phase 5: vendor research specialist first; execute only verified adapters; hardware-test operator with reboot evidence.
- Phase 6: release executor, tester, code reviewer, then user acceptance.

## Program Checklist

- [ ] Phase 0 locks target inventory, protocol, mode flags, electrical caveats, and per-family reset verdicts.
- [ ] Phase 1 introduces stable ids, immutable capability snapshots, ownership generations, dispatcher barriers, and v3 migration.
- [ ] Phase 1 fixes duplicate `ENE DRAM` collisions and removes device-name keys from active runtime paths.
- [ ] Phase 1 routes blackout, retry, stop, resize, and thermal writes through one dispatcher.
- [ ] Phase 2 replaces the broken fixed Tk settings view with the PySide6 device/zone/LED workspace.
- [ ] Phase 2 delivers staged manual color selection with scope preview and capability-aware controls.
- [ ] Phase 3 delivers independent JRAINBOW1/JRAINBOW2 counts, validation, readback, restart persistence, and topology help.
- [ ] Phase 4 exposes reported hardware modes/parameters and keeps temperature synchronization as an explicit ownership mode.
- [ ] Phase 4 separates app profiles from optional device persistence and tests mode transitions.
- [ ] Phase 5 implements only vendor-default adapters that reached `SUPPORTED_VERIFIED` in Phase 0.
- [ ] Phase 5 proves reset with app stopped, profile disabled, and cold boot; no snapshot/preset substitution.
- [ ] Phase 6 validates clean install, upgrade, rollback, sleep/wake, reboot, cold boot, stale sensors, disconnect/reconnect, and performance.
- [ ] Every phase has a durable report, regression results, user confirmation, and honest status.
- [ ] Final README/troubleshooting text removes the misleading claim that `Reset to Original` is factory reset.

## Verification Evidence

The final release evidence bundle must include:

- dependency lock and build hashes;
- sanitized discovery snapshot showing distinct device ids;
- automated test outputs and coverage list;
- screenshots of every principal UI state, including unsupported reset;
- command log proving single-writer ordering and stale-command rejection;
- JRAINBOW1/2 before/after/readback/restart records;
- per-family reset research verdict and, where supported, video/photos/logs covering pre-reset, app shutdown, cold boot, and default state before profile application;
- clean install/upgrade/uninstall results and prior-installer rollback result;
- sleep/wake/reboot and 30-minute thermal performance logs.

## Resume and Execution Handoff

Read this umbrella, the exact selected phase plan, the latest report from every dependency phase, `process/context/all-context.md`, and `process/context/tests/all-tests.md`. Check `git status` before acting. The only valid next execute target is:

`process/features/unified-rgb-control/active/PHASE_0_RESET_CAPABILITY_RESEARCH_PLAN_20-09-26.md`

Phase 0 is research-only and must finish its evidence report before Phase 1 can enter EXECUTE.
