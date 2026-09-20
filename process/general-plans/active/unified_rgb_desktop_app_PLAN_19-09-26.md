# Unified RGB Desktop App Implementation Plan

**Date**: 19-09-26  
**Complexity**: COMPLEX — standard complex, one authoritative plan, one sequential execution stream  
**Status**: ⏳ PLANNED  
**Execution model**: RFC-by-RFC with pre-phase research, approval, implementation, verification, and user confirmation

## Overview

Turn the existing Windows tray utility into one installable product: one installer, one Start Menu entry, one tray icon, and one settings window. The product will privately supervise a pinned OpenRGB 1.0 portable engine and a small self-contained .NET sensor bridge, so the user no longer has to install, configure, or launch OpenRGB or Core Temp manually. Existing temperature gradients, smoothing, per-device/per-LED brightness, CPU/GPU mapping, screensaver behavior, startup option, tray actions, and user configuration must survive the migration.

This is intentionally a **standard complex** plan rather than a phase program. The work crosses Python, .NET, Windows process management, hardware access, and packaging, but it has one product boundary, one release candidate, one hardware acceptance matrix, and one ordered implementation stream. Each RFC still has a hard proof gate; all work remains in this single file so an execution agent has one source of truth.

## Quick Links

- [Context and Goals](#1-context-and-goals)
- [Phase Completion Rules](#2-phase-completion-rules)
- [Execution Brief](#3-execution-brief)
- [Architecture Decisions](#6-architecture-decisions-final)
- [Security Posture](#9-security-posture)
- [Phased Delivery Plan](#16-phased-delivery-plan)
- [RFCs](#18-rfcs)
- [Touchpoints](#touchpoints)
- [Public Contracts](#public-contracts)
- [Blast Radius](#blast-radius)
- [Verification Evidence](#verification-evidence)
- [Resume and Execution Handoff](#resume-and-execution-handoff)
- [Implementation Checklist](#28-implementation-checklist)

## 1. Context and Goals

### Current runtime

The RGB product currently consists of three independently managed applications:

1. `src/openrgb_tray_app.py` / `OpenRGBTempSync.exe` owns the tray UI, settings, smoothing, temperature-to-color mapping, and LED updates.
2. An externally installed OpenRGB instance must already expose its SDK server at `127.0.0.1:6742`.
3. Core Temp must already expose `CoreTempMappingObjectEx` for CPU temperatures.

GPU temperature is read separately through NVIDIA NVML. Configuration is stored beside the executable in `config.json`; startup uses `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. The Python app is currently a 1,051-line mixed UI/runtime module with broad exception swallowing. `src/openrgb_temp_sync.py` is an older CLI path, and `src/test_openrgb_sync.py` tests that older module rather than the current tray controller. The active `rgb_brightness_config_PLAN_31-05-26.md` is a historical predecessor for brightness/settings behavior and is not an overlapping one-app packaging plan.

The repository also contains a Newton web simulator (`index.html`, `src/main.js`, `src/style.css`, `src/physics.test.js`, Vite configuration). It is unrelated to the Windows RGB runtime and must not be bundled, moved, or deleted by this work.

### Target hardware and operating system

- Windows 11 x64.
- AMD Ryzen 7 5800X.
- MSI MAG B550 TOMAHAWK (`MS-7C91`) and its JRGB/JRAINBOW/onboard zones.
- Two G.Skill RGB DIMMs exposed by OpenRGB as `ENE DRAM` with eight reported LEDs.
- Gigabyte AORUS GeForce RTX 3060 ELITE LHR with five reported RGB zones.
- OpenRGB 1.0 stable, SDK protocol 6.

### Product goal

After one elevated installer completes, a normal user workflow is:

1. Launch **OpenRGB Temp Sync** once or let its single startup entry run.
2. See one tray icon.
3. Open one settings window to configure all detected supported devices.
4. Never manually launch or configure OpenRGB or Core Temp.

### Success metrics

- Fresh Windows 11 x64 install reaches `Running` without a separately installed OpenRGB or Core Temp.
- The target CPU, GPU, RAM, mainboard, and GPU RGB controller pass the hardware matrix in Section 21.
- SDK port 6742 is never listening on a non-loopback interface.
- Startup creates only one product task and one visible tray icon.
- CPU and GPU readings update at least once every two seconds; LED animation remains at the current 20 Hz target without UI blocking.
- Existing `config.json` values migrate without loss, with the original retained as a recoverable backup.
- App/child crash, port conflict, missing driver, and sensor loss become visible degraded states rather than silent failure.
- Installer, installed files, third-party notices, checksums, uninstall, and rollback all pass the release checklist.

## 2. Phase Completion Rules

A phase is NOT complete until:

1. **Integration Test** — It works with the other product pieces.
2. **Manual Test** — The user can perform the affected workflow.
3. **Data Verification** — Configuration, process, port, registry/task, installed-file, or hardware state is inspected and confirmed. There is no database in this product.
4. **Error Handling** — Defined failure cases fail safely and visibly.
5. **User Confirmation** — The user says the phase works on the target PC.

Status meanings:

- ⏳ PLANNED — Not started.
- 🔨 CODE DONE — Written but not end-to-end tested.
- 🧪 TESTING — Currently being tested.
- ✅ VERIFIED — Tested and user-confirmed working.
- 🚧 BLOCKED — A real blocker prevents completion.

After each phase, document:

- [ ] Manual behavior tested.
- [ ] Relevant state inspected and recorded.
- [ ] Errors encountered and fixed or explicitly routed.
- [ ] User confirmation received.

No RFC may advance to the next RFC until its verification checklist is complete. A build, import, or unit-test pass alone is never enough for `✅ VERIFIED`.

## 3. Execution Brief

### Phase 0: Baseline and dependency lock

**What happens:** Capture current hardware/process/config behavior, verify exact OpenRGB 1.0 CLI behavior on the pinned binary, lock all artifact versions, hashes, licenses, and source bundles, and prove the existing config can be parsed before changing runtime code.

**Integration points:** Current Python app, OpenRGB SDK v6, installed PawnIO state, target hardware, dependency manifest, and release source notices.

**Test:** Run dependency checksum verification; enumerate the three target RGB controller families and CPU/GPU sensors; capture current port bindings and screenshots.

**Verify:** The baseline report records exact device/LED names and counts, sensor identifiers, OpenRGB command-line output, hashes, and whether a reboot is required after PawnIO installation.

**Done when:** The user confirms the baseline matches the physical machine and approves implementation from the locked manifest.

### Phase 1: Testable Python core and configuration migration

**What happens:** Separate lighting math, configuration, orchestration, and UI responsibilities while preserving behavior. Introduce schema version 2 and migrate legacy side-by-side config into per-user LocalAppData.

**Integration points:** Existing `config.json`, tray controller, OpenRGB device metadata, startup setting, and test suite.

**Test:** Python unit tests cover gradient boundaries, brightness, EMA/transition interpolation, legacy migration, invalid/corrupt config, unmatched devices, and atomic saves.

**Verify:** A migrated v2 file reproduces every current threshold, color, brightness, mapping, transition, and screensaver value; the original remains unchanged.

**Done when:** Automated tests pass and the user confirms the migrated settings shown in the UI are identical.

### Phase 2: Internal sensor bridge

**What happens:** Replace Core Temp shared memory and direct NVML access with a pinned, self-contained .NET 8 x64 helper using LibreHardwareMonitorLib 0.9.6. The Python supervisor owns the helper and consumes versioned NDJSON from stdout.

**Integration points:** LibreHardwareMonitor, elevated runtime, Python subprocess reader, smoothing loop, status UI, and logs.

**Test:** .NET selector tests, Python protocol parser tests, malformed/stale stream tests, helper crash recovery, and live CPU/GPU comparison against an independent monitor.

**Verify:** Ryzen 7 5800X and RTX 3060 values remain non-null under idle/load and are within the agreed tolerance of a trusted comparison tool.

**Done when:** Core Temp can be closed/uninstalled and the user confirms both CPU- and GPU-driven LEDs still react correctly.

### Phase 3: Private OpenRGB engine supervision

**What happens:** Bundle and supervise OpenRGB 1.0 portable. Reuse a pre-existing server only when it is loopback-only, owned by an OpenRGB process, and protocol-compatible; otherwise fail with an actionable conflict. Owned children are started, health-checked, restarted with limits, and terminated by a Windows Job Object.

**Integration points:** Port 6742, OpenRGB SDK client, child lifecycle, PawnIO, app status, Direct mode, and LED update loop.

**Test:** Clean port, compatible local server, unrelated listener, wildcard listener, child crash, delayed scan, zero devices, SDK disconnect, and app exit.

**Verify:** `Get-NetTCPConnection` shows only loopback binding; Task Manager shows hidden children; the app never terminates an external server.

**Done when:** All three target controller families are detected and controllable without manually opening OpenRGB.

### Phase 4: One-app UX and startup

**What happens:** Make the runtime single-instance, retain one tray/settings surface, add clear engine/sensor/device status, replace the Run registry entry with one highest-privilege per-user Scheduled Task, and keep all existing controls.

**Integration points:** Tkinter, pystray, Windows elevation, named mutex/event activation, Task Scheduler, screensaver detection, and configuration.

**Test:** Manual launch, second launch, logon launch, enable/disable startup, settings save/reload, screensaver, lights off/on, engine retry, and exit.

**Verify:** One product process tree, one tray icon, one Start Menu entry, one scheduled task, and no OpenRGB/Core Temp startup entries created by this product.

**Done when:** The user completes the full workflow after a reboot without touching another lighting or monitoring app.

### Phase 5: Installer, legal payload, uninstall, and release

**What happens:** Publish the Python app as an onedir bundle, include the self-contained helper and verified OpenRGB payload, build one Inno Setup installer, handle PawnIO, ship complete notices/source, and exercise upgrade/uninstall/rollback.

**Integration points:** PyInstaller, .NET publish, vendor staging, Inno Setup, code signing when available, Programs and Features, backups, and release evidence.

**Test:** Clean install, upgrade over legacy app, repair/reinstall, cancel, reboot-required path, uninstall keeping settings, optional settings removal, and previous-installer rollback.

**Verify:** Installed hashes match the manifest; no child remains after uninstall; owned tasks/shortcuts/files are removed; shared PawnIO and user config follow the documented retention policy.

**Done when:** The user accepts a release candidate installed from the single installer and the complete hardware matrix is green.

### Expected Outcome

- One offline-capable Windows installer.
- One visible application, one Start Menu entry, and one tray icon.
- Hidden, app-owned OpenRGB and sensor-helper processes.
- No Core Temp dependency.
- Honest support wording: devices detected and supported by the bundled OpenRGB engine.
- Preserved current lighting behavior and recoverable configuration migration.
- Reproducible dependency and licensing record.
- Safe uninstall and rollback path.

## 4. Phased Execution Workflow

For every RFC:

1. **Pre-Phase Research** — Re-read this RFC, inspect current code and machine state, run only read-only discovery, present findings, and **STOP** for user approval.
2. **Detailed Planning Check** — Confirm exact files, dependencies, commands, risks, and evidence; update this plan if repo or hardware truth differs; obtain approval.
3. **Implementation** — Implement only the selected RFC. Do not silently widen scope.
4. **Testing and Verification** — Run the RFC's automated, integration, failure, and manual procedures. Record exact commands and outcomes.
5. **User Confirmation** — Present:
   - **What's Functional Now**
   - **What Was Tested**
   - **What You Can Test**
   - **Ready For**

Example execution boundary:

- User selects RFC-001.
- Agent inspects the exact OpenRGB archive, `--help` output, device enumeration, sensor identifiers, existing config, and dependency metadata.
- Agent presents facts, discrepancies, and locked hashes, then **pauses without editing source**.
- User approves.
- Agent updates the dependency manifest/acquisition scripts and tests only within RFC-001.
- Agent runs the checksum/baseline gates and presents evidence.
- User confirms; only then does RFC-002 begin.

## 5. Non-Goals and Constraints

### In scope

- Windows 11 x64 desktop/tray product.
- One installer and one visible UI surface.
- App-owned OpenRGB 1.0 portable and sensor bridge.
- PawnIO prerequisite flow needed for the target RAM/mainboard.
- CPU/GPU temperature sources.
- Existing gradient, EMA, transition, per-device/per-LED brightness and source mapping.
- Screensaver pause, lights toggle, startup, tray, config migration, logs, diagnostics.
- Upgrade, uninstall, rollback, licensing, checksums, and source notices.

### Out of scope

- A claim to support every RGB device in existence.
- Vendor-specific SDK backends or a plugin system.
- Remote SDK access, LAN control, cloud accounts, telemetry, or automatic update service.
- OpenRGB GUI exposure as part of normal usage.
- Rewriting the product in C++/Qt, C#, Electron, or a web stack.
- RGB audio/game integrations, scenes, profiles beyond current temperature behavior, or remote control.
- Moving or deleting the unrelated Newton simulator.
- Controlling fans, voltages, clocks, or any non-lighting hardware.
- Silent removal of third-party applications, drivers, user profiles, or user configuration.

### Constraints

- Preserve user-owned/unrelated dirty worktree changes.
- Use `apply_patch` for source edits during EXECUTE.
- Do not ship the current machine-specific `config.json` as a default for other users.
- Do not bind any control protocol to `0.0.0.0` or a LAN interface.
- No runtime downloads; release builds stage only checksum-verified artifacts.
- No administrative action outside installer/startup/runtime needs.
- The app may require elevation because both PawnIO-backed RGB detection and some sensors require it.

## 6. Architecture Decisions Final

### AD-001: Keep Python as the visible application

**Decision:** Retain Python/Tkinter/pystray and refactor the current behavior into focused modules.

**Rationale:** The working UI and lighting logic already exist. Rewriting the product would increase risk without improving the one-app user outcome.

**Implications:** PyInstaller remains in the build chain; Python dependency licensing and hashes must be managed; current behavior can be regression-tested before process integration.

### AD-002: Ship an onedir app inside one installer

**Decision:** Use a PyInstaller onedir build, not a onefile executable. The user still receives one installer and one visible app entry.

**Rationale:** Onedir avoids onefile extraction races, makes the two internal executables and legal payload deterministic, reduces antivirus false positives, and simplifies repair/rollback.

**Implications:** Internal files are installed under `%ProgramFiles%\OpenRGB Temp Sync\`; writable state lives under `%LOCALAPPDATA%\OpenRGBTempSync\`.

### AD-003: Pin OpenRGB stable 1.0 x64 portable

**Decision:** Vendor `OpenRGB_1.0_Windows_64_81bbe18.zip` from the official release, commit `81bbe18`, SDK protocol 6, SHA-256 `182A52A3C97C4C4AE52C80286B4260C9666C51C3447DBC416EE8945F66192E90`.

**Rationale:** Stable 1.0 is the approved engine, includes the current protocol/device work, and separates the engine cleanly as an unmodified child executable.

**Implications:** Build staging must reject any different digest. The exact source archive and GPL-2.0-or-later text are shipped. Pipeline/nightly artifacts are forbidden for v1 release builds.

### AD-004: Use openrgb-python 0.3.7

**Decision:** Pin `openrgb-python==0.3.7`; wheel SHA-256 `2188636e7a5831a8030abe34b234ede8d4a263ba02bc903d975eb55a80551833`.

**Rationale:** This release followed OpenRGB 1.0 and is the minimum evidence-backed client candidate for SDK v6. Pre-phase compatibility tests remain mandatory.

**Implications:** The SDK negotiation result is a release gate. Because the package is GPLv3, distribution must include its license/corresponding source and the application source under a compatible distribution model; legal review is required before public release.

### AD-005: Use a long-running .NET 8 sensor bridge with LibreHardwareMonitorLib 0.9.6

**Decision:** Create a self-contained `win-x64` console helper using stable `LibreHardwareMonitorLib` 0.9.6, source revision `3d331e3370efb858411f19511373eff65a218701`. Communicate by NDJSON over redirected stdout; diagnostics go to stderr.

**Rationale:** LibreHardwareMonitor supports AMD CPUs and NVIDIA GPUs, while a small bridge avoids embedding .NET inside Python and removes Core Temp/NVML-specific paths. Standard process pipes require no new listening port.

**Implications:** The bridge runs with the parent privilege level, stays open to avoid repeated hardware initialization, emits versioned data, and is published self-contained. Its NuGet lock, package checksum, MPL-2.0 license, third-party notices, and .NET runtime notices are shipped.

### AD-006: One elevated process tree, not a custom Windows service

**Decision:** Mark the visible app `requireAdministrator`; create one per-user logon Scheduled Task with highest privileges when startup is enabled. The app launches both internal children hidden.

**Rationale:** Target RAM/mainboard detection through PawnIO and some sensor access require elevation. A custom service plus IPC would add another permanent component and trust boundary.

**Implications:** Manual cold launch can show UAC; startup launch uses the approved task after install. The installer explains why elevation is needed. No app service is installed in v1.

### AD-007: Bind OpenRGB exclusively to loopback

**Decision:** Start the verified bundled binary with its server enabled, host `127.0.0.1`, port `6742`, no auto-connect, a dedicated config directory, warning-level logs, and no GUI personality. Exact spellings must be confirmed from the pinned binary's `--help` output during RFC-001.

**Rationale:** The SDK is an unauthenticated local control channel and historical versions exposed risky wildcard listeners.

**Implications:** A wildcard/LAN binding is a hard failure. The firewall is defense-in-depth, not the primary control. Port ownership and bind address are verified before connection.

### AD-008: Safely reuse but never own a compatible existing server

**Decision:** If port 6742 is occupied, identify the listener PID/image and bind address using Windows APIs. Reuse it only if all conditions pass: loopback-only binding, image is OpenRGB, SDK negotiation succeeds at protocol 5 or 6, and device enumeration returns a structurally valid response. Otherwise block with an actionable conflict message.

**Rationale:** Blind connection could talk to an unrelated or remotely exposed process; blindly killing a process could destroy user state.

**Implications:** Externally owned OpenRGB is never restarted or terminated. The UI labels it `External OpenRGB`. The app does not promise one icon if the user deliberately runs the external GUI; the bundled default remains iconless.

### AD-009: Supervise owned children with a Windows Job Object

**Decision:** Assign bundled OpenRGB and the sensor bridge to a kill-on-close Job Object. Use bounded exponential restart with at most three restarts in 60 seconds, followed by a visible degraded state and manual Retry action.

**Rationale:** Children must not leak after crash/uninstall, and unlimited restart loops can hammer hardware buses.

**Implications:** External OpenRGB never joins the Job Object. Graceful termination is attempted before job teardown. Logs retain the last failure.

### AD-010: Move writable state to LocalAppData with schema versioning

**Decision:** Store config, logs, backups, and the private OpenRGB config under `%LOCALAPPDATA%\OpenRGBTempSync\`. Introduce config schema version 2 with atomic save and migration from the legacy executable-adjacent file.

**Rationale:** Program Files is not writable and side-by-side config is fragile during upgrades.

**Implications:** First run copies and migrates; it never overwrites the legacy input. Corrupt files are quarantined and defaults are generated with a visible warning.

### AD-011: Prefer stable device identity while preserving unmatched legacy data

**Decision:** V2 device profiles use a stable key derived from OpenRGB vendor/product/serial/location metadata and retain `last_seen_name`. LED entries use reported name plus duplicate occurrence index. Legacy migration matches exact device name first, then a unique LED-name/count signature; ambiguous profiles remain in `unmatched_legacy_profiles` for manual reassignment.

**Rationale:** OpenRGB upgrades can rename or reorder controllers. Silent fuzzy assignment could send wrong brightness/source settings to hardware.

**Implications:** No legacy settings are discarded. UI shows unmatched profiles and permits explicit reassignment; v1 does not add a general plugin/device abstraction.

### AD-012: Use Inno Setup 6.7.3 for a single offline installer

**Decision:** Pin Inno Setup 6.7.3 and build one x64 installer that contains all runtime/vendor/legal payloads.

**Rationale:** It is a mature Windows-native path with elevation, uninstall, upgrade, rollback-oriented scripting, hash checks, and Programs and Features integration.

**Implications:** The compiler version is recorded in the manifest. Code signing is used when a certificate is available; absence of signing must be disclosed and manually tested with SmartScreen/Defender.

## 7. Architecture Clarification

The phrase “one app” is a UX and installation contract, not a single-process or single-file constraint.

Visible/user-managed surface:

- `OpenRGBTempSync.exe`: tray, settings, orchestration, lighting loop.

Hidden implementation processes:

- `OpenRGB.exe`: unmodified private RGB engine/server.
- `OpenRGBTempSync.SensorBridge.exe`: temperature sensor bridge.

No additional tray icons, consoles, services, configuration tools, or startup entries are created by the default path. This is the minimum architecture that preserves OpenRGB hardware breadth and eliminates Core Temp.

## 8. High-Level Data Flow

1. Installer elevates, verifies payloads, installs product files, handles PawnIO, and optionally creates the startup task.
2. App obtains a per-user single-instance mutex; a second launch signals the running instance to show Settings and exits.
3. Configuration loader migrates or validates schema v2 under LocalAppData.
4. Runtime supervisor inspects `127.0.0.1:6742`.
5. Supervisor either reuses a validated external OpenRGB server or launches the bundled verified OpenRGB child.
6. Supervisor launches the sensor bridge and validates its hello record.
7. Sensor bridge updates LibreHardwareMonitor and emits timestamped CPU/GPU samples once per second.
8. Python reader rejects malformed, wrong-schema, non-finite, out-of-range, or stale samples.
9. Lighting loop applies EMA, source mapping, temperature gradient, brightness, and transition interpolation.
10. SDK client sends per-LED colors to supported/detected OpenRGB controllers at the current 20 Hz target.
11. Tray/UI displays runtime state; settings are atomically persisted.
12. On exit, owned children are stopped and the Job Object guarantees cleanup; external processes remain untouched.

## 9. Security Posture

### Trust boundaries

- **Installer to vendored payload:** every artifact must match a committed SHA-256 manifest before packaging and again during release verification.
- **App to OpenRGB SDK:** connect only to loopback after verifying listener address, process identity, protocol negotiation, and response structure.
- **App to sensor helper:** parent-created anonymous pipes only; no TCP/HTTP endpoint.
- **Config/log input:** all JSON/NDJSON is treated as untrusted; enforce schema, type, range, length, and size limits.
- **Elevation:** no shell command concatenation; use explicit argument arrays and absolute paths.

### Required controls

- Refuse `0.0.0.0`, `::`, LAN, or non-loopback OpenRGB listeners.
- Never trust a port-open check alone.
- Never terminate a process not started by this app.
- Use `%ProgramFiles%` read-only payloads and `%LOCALAPPDATA%` writable state.
- Restrict config/log permissions to the current user where Windows inheritance does not already do so.
- Do not place secrets, credentials, machine serials, or full config content in normal logs.
- Redact user profile paths when exporting diagnostics where practical.
- Cap logs by size/count and cap child restart attempts.
- Validate temperatures to a sane configurable hard range of `0–130 °C`; null or stale data must not be converted to a plausible fake reading.
- On sensor loss, hold the last valid color only for a short documented grace period, then pause updates and show `Sensor unavailable`; do not drive LEDs to a misleading “cool” color.
- On engine loss, stop sends, reconnect with backoff, and show `RGB engine unavailable`.
- Do not open inbound Windows Firewall rules.

### High-risk evidence

This work touches elevated execution, a local control protocol, a kernel driver prerequisite, and installer/uninstall behavior. Before release, create a manual-first evidence pack under `process/general-plans/reports/harness/unified-rgb-desktop-app/` containing:

- `risk-gate.json`
- `context-snippets.json`
- `verification.json`
- `review-decision.json`
- `adversarial-validation.json`

No final release claim is allowed until the risk gate and reviewer decision are present.

## 10. Component Details

### Python application entrypoint

**Path:** `src/openrgb_tray_app.py`

Responsibilities:

- Resolve installed/dev resource paths.
- Acquire single-instance guard.
- Initialize logging and config.
- Compose supervisor, lighting controller, tray, and settings UI.
- Run Tk main loop on the main thread.
- Coordinate graceful shutdown.

It must not contain sensor protocol parsing, OpenRGB launch policy, configuration migration, or color math after refactor.

### Configuration module

**Path:** `src/openrgb_temp_sync/config.py`

Responsibilities:

- Define schema v2 defaults and validation.
- Locate LocalAppData state.
- Load/migrate v1 data.
- Atomically save via temp file plus replace.
- Maintain timestamped backups.
- Resolve stable device/LED profiles without deleting unmatched data.

### Lighting core

**Path:** `src/openrgb_temp_sync/lighting.py`

Responsibilities:

- Temperature-to-gradient mapping.
- Brightness scaling and clamping.
- EMA temperature smoothing.
- Per-frame RGB interpolation.
- CPU/GPU source resolution.
- Pure functions/classes with no UI, filesystem, or hardware calls.

### OpenRGB runtime

**Path:** `src/openrgb_temp_sync/openrgb_runtime.py`

Responsibilities:

- Inspect port/listener ownership.
- Verify bundled executable hash before launch.
- Launch with explicit safe flags and hidden window.
- Negotiate SDK and enumerate devices.
- Track owned versus external lifecycle.
- Health-check, bounded restart, and graceful shutdown.

### Sensor runtime

**Path:** `src/openrgb_temp_sync/sensor_runtime.py`

Responsibilities:

- Launch hidden helper from an absolute path.
- Validate hello/sample NDJSON records.
- Maintain last valid timestamp and latest CPU/GPU readings.
- Drain stderr into capped logs.
- Detect stale stream, restart with limits, and expose health.

### Runtime coordinator

**Path:** `src/openrgb_temp_sync/controller.py`

Responsibilities:

- Own the lifecycle state machine.
- Run lighting updates without blocking Tk.
- Apply Direct mode safely.
- Handle screensaver/lights-off/start/stop/retry.
- Publish immutable status snapshots to UI.

### UI module

**Path:** `src/openrgb_temp_sync/ui.py`

Responsibilities:

- Preserve the existing two settings tabs and tray actions.
- Show engine type/status, sensor values/source names, device count, startup status, unmatched profiles, and last error.
- Marshal all Tk operations onto the main thread.
- Provide Retry and Export Diagnostics actions.

### Sensor bridge

**Paths:**

- `sensor-bridge/OpenRGBTempSync.SensorBridge.csproj`
- `sensor-bridge/Program.cs`
- `sensor-bridge/SensorSelector.cs`
- `sensor-bridge/SensorProtocol.cs`

Responsibilities:

- Enable only CPU and GPU hardware categories.
- Open LibreHardwareMonitor once and update once per configured interval.
- Choose target sensors deterministically.
- Emit a hello record and timestamped sample records.
- Return distinct exit codes for startup, permission/driver, and fatal enumeration errors.
- Close hardware cleanly on parent shutdown/pipe closure.

### Build and installer

**Paths:**

- `OpenRGBTempSync.spec`
- `scripts/fetch-vendor.ps1`
- `scripts/build-sensor-bridge.ps1`
- `scripts/build-app.ps1`
- `scripts/build-installer.ps1`
- `scripts/verify-release.ps1`
- `installer/OpenRGBTempSync.iss`
- `third_party/dependencies.lock.json`
- `third_party/THIRD-PARTY-NOTICES.md`

Responsibilities:

- Reproducibly acquire/stage exact dependencies.
- Reject hash/version drift.
- Build helper, onedir Python app, and one installer.
- Include notices/source archives.
- Validate installed layout and manifest.

## 11. Internal Process and IPC Surface

There is no web backend, database, REST API, or remote worker.

### OpenRGB child command contract

The child command is an absolute path under the install directory. Required semantic options are:

- server mode enabled;
- server host exactly `127.0.0.1`;
- server port exactly `6742` in v1;
- auto-connect disabled;
- private config directory under LocalAppData;
- warning-or-higher logging;
- no GUI/start-minimized option that creates a second tray icon.

RFC-001 must record the exact option spellings emitted by the pinned binary and fail if the binary does not support this contract.

### Sensor NDJSON contract

Record types and required fields:

| Record | Required fields | Rules |
|---|---|---|
| `hello` | `schema`, `bridge_version`, `library_version`, `pid`, `interval_ms` | Must be the first valid record; schema must equal 1. |
| `sample` | `schema`, `seq`, `timestamp_utc`, `cpu_c`, `gpu_c`, `cpu_source`, `gpu_source`, `warnings` | Temperatures are finite number or null; sequence is monotonic; timestamp is UTC; sources include hardware ID and sensor ID/name. |
| `fatal` | `schema`, `code`, `message` | Message is bounded and safe for logs/UI; process exits nonzero after emission. |

Parser limits:

- UTF-8, one object per line.
- Maximum line length 64 KiB.
- Reject unknown schema versions.
- Ignore unknown additive fields for forward compatibility.
- Reject non-monotonic sequence, future-skewed timestamps, and samples older than five seconds.

### Process exit codes

| Process | Exit meaning |
|---|---|
| Sensor bridge `0` | Clean parent-driven shutdown. |
| Sensor bridge `10` | Invalid arguments/config. |
| Sensor bridge `20` | Hardware initialization/permission failure. |
| Sensor bridge `30` | No usable CPU or GPU sensor found. |
| Sensor bridge `40` | Fatal runtime/update error. |
| App `0` | Clean exit or activation handed to existing instance. |
| App nonzero | Startup contract failure before tray is usable; error must be logged and shown when possible. |

## 12. Configuration Schema and Migration

### Schema v2 top-level contract

| Field | Purpose |
|---|---|
| `schema_version` | Integer `2`. |
| `thermal` | Low/mid/high thresholds and RGB colors, EMA factor, transition speed. |
| `behavior` | Screensaver pause, startup preference, lights-off persistence policy. |
| `devices` | Stable-keyed device profiles and per-LED brightness/source. |
| `unmatched_legacy_profiles` | Preserved v1 mappings that cannot be assigned safely. |
| `runtime` | Local engine port fixed to 6742, last migration version, diagnostic preferences. |

### Migration rules

1. Search LocalAppData v2 first.
2. If absent, search legacy config beside the running executable and repository root in dev mode.
3. Read legacy JSON with a 1 MiB size limit.
4. Validate threshold order, colors, brightness, source values, transition speed, and booleans.
5. Preserve recognized fields exactly.
6. Preserve unknown/unmatched device data rather than dropping it.
7. Write `config.v1.<timestamp>.bak.json` under LocalAppData backups.
8. Atomically write v2.
9. Record migration source and result in logs without dumping the full config.
10. Never edit or delete the original legacy file automatically.

### Invalid-state behavior

- Missing file: use defaults and persist only after first save.
- Malformed JSON/schema: quarantine a copy, load defaults, show warning.
- Invalid individual field: use the documented default for that field and record validation error; never crash the tray.
- Write failure: retain in-memory prior config, show error, and do not claim save success.
- Device mismatch: preserve unmatched profile and require explicit reassignment.

## 13. Sensor Selection Rules

### CPU

Restrict candidates to `HardwareType.Cpu` and `SensorType.Temperature`. Choose in this order:

1. Previously persisted exact sensor identifier, if still present.
2. Exact normalized name `Core (Tctl/Tdie)`.
3. Exact normalized name `CPU Package`.
4. Exact normalized name `Core Average`.
5. If no match, emit null plus a warning containing available bounded sensor metadata; do not guess among CCD/core/max sensors.

### GPU

Restrict candidates to NVIDIA GPU hardware for the target system and temperature sensors. Choose in this order:

1. Previously persisted exact sensor identifier.
2. Exact normalized name `GPU Core`.
3. Exact normalized name `GPU Package`.
4. If exactly one temperature sensor remains, use it.
5. Otherwise emit null plus a warning; do not guess.

### Sampling and health

- Default sample interval: 1,000 ms.
- Python EMA factor preserves current `0.15` behavior unless config explicitly overrides it.
- Last valid sample grace: five seconds.
- At ten seconds stale, transition to `Sensor unavailable`, stop new LED writes, and expose Retry.
- Sensor IDs/names are displayed in diagnostics to support hardware troubleshooting.

## 14. Runtime State Model

| State | Meaning | User-visible behavior |
|---|---|---|
| `STARTING` | Config and children initializing. | Gray tray; status shows current step. |
| `RUNNING_OWNED` | Bundled engine and helper healthy. | Dynamic tray color; normal controls. |
| `RUNNING_EXTERNAL` | Compatible external engine plus owned helper healthy. | Normal controls plus `External OpenRGB` label. |
| `PAUSED` | User stopped sync or screensaver pause active. | No LED updates; reason visible. |
| `LIGHTS_OFF` | User requested black output. | One black write then no redundant 20 Hz flood. |
| `DEGRADED_ENGINE` | SDK/engine unavailable. | Sensor may continue; no RGB writes; Retry enabled. |
| `DEGRADED_SENSOR` | Sensor stream unavailable/stale. | No misleading color updates; engine remains connected; Retry enabled. |
| `CONFLICT` | Unsafe/incompatible port owner or competing RGB software. | Clear remediation; no process termination. |
| `STOPPING` | Graceful shutdown underway. | Menu disabled except status. |

All state transitions must be serialized by the controller. UI reads snapshots and never mutates runtime internals directly.

## 15. Packaging, Driver, Licensing, and Redistribution

### Locked release inputs

| Dependency | Pin | Integrity/source requirement |
|---|---|---|
| OpenRGB Windows x64 portable | 1.0, commit `81bbe18`, SDK 6 | Archive SHA-256 fixed in AD-003; official URL and source archive recorded. |
| openrgb-python | 0.3.7 | Wheel SHA-256 fixed in AD-004; sdist/source and GPLv3 text included. |
| LibreHardwareMonitorLib | 0.9.6, commit `3d331e3...` | NuGet lock and package SHA-512/SHA-256 captured; nupkg/source, MPL-2.0, and upstream third-party notices included. |
| .NET runtime | .NET 8 self-contained win-x64 patch selected by locked SDK | SDK/runtime versions and runtime license/notices captured in manifest. |
| Python | CPython 3.12 x64 exact patch selected for build | Runtime license and build fingerprint included. |
| Pillow | 12.3.0 | Hash-locked Python requirements. |
| pystray | 0.19.5 | Hash-locked Python requirements. |
| PyInstaller | 6.22.3 | Build-only pin and hash lock. |
| Inno Setup | 6.7.3 | Build-only compiler fingerprint. |
| PawnIO | Exact version shipped/required by OpenRGB 1.0 | RFC-001 must lock signed installer/module version, publisher, hash, license, and silent flags before packaging. |

No dependency marked “latest” is permitted in the build. Python dependencies and transitives are generated into a hash-locked requirements file; NuGet uses a lock file in locked mode.

### License obligations

- **OpenRGB GPL-2.0-or-later:** keep OpenRGB unmodified and separate; include copyright notices, full license, exact corresponding source archive, build/source identification, and warranty disclaimer.
- **openrgb-python GPLv3:** include full license and exact source. Because it is bundled/imported into the application executable, publish the corresponding application source under a GPLv3-compatible license or obtain legal review before distribution.
- **LibreHardwareMonitor MPL-2.0:** include MPL text, exact package/source, upstream third-party notices, and source for any modified MPL-covered files. Prefer no library modifications.
- **PawnIO, .NET, CPython, Pillow, pystray, PyInstaller, Inno Setup, and transitives:** copy exact upstream license/notices into the installed `licenses/` tree and summarize them in `THIRD-PARTY-NOTICES.md`.
- Include a `sources/` directory in the installer so source availability does not depend on a future website.
- Legal compliance is a release blocker, not a post-release documentation task.

### PawnIO handling

1. Installer checks the exact driver/service/package identity and version without modifying state.
2. If the pinned compatible version is present, reuse it.
3. If absent/incompatible, present a clear prerequisite step and install the pinned, signature-verified package with elevation.
4. If installation requires reboot, finish installation safely, mark RGB runtime pending, and resume verification after reboot.
5. App health reports `PawnIO unavailable` separately from `No devices`.
6. Uninstall removes product-owned files/tasks/processes. PawnIO is treated as shared and retained by default; optional removal is offered only if this installer recorded that it installed PawnIO, with a warning that other software may depend on it.

### Upgrade and rollback

- Use a stable AppId and upgrade code/path.
- Before replacing files, stop only the product's running instance and owned children.
- Back up LocalAppData config and the prior installed manifest.
- Install into a versioned staging location, verify hashes, then switch the active install.
- On failure, restore the prior files/task/config pointer and report rollback.
- Keep the previous signed installer with release artifacts for manual rollback.
- Never downgrade/mutate the user's external OpenRGB configuration.

## 16. Phased Delivery Plan

| Phase | RFC | Status | What green proves |
|---|---|---|---|
| 0 | RFC-001 | ⏳ PLANNED | Dependencies, licenses, hardware baseline, and exact CLI/protocol assumptions are real and reproducible. |
| 1 | RFC-002 | ⏳ PLANNED | Existing behavior is protected by tests and legacy config migrates without loss. |
| 2 | RFC-003 | ⏳ PLANNED | Core Temp/NVML dependency is replaced by a reliable internal sensor stream. |
| 3 | RFC-004 | ⏳ PLANNED | OpenRGB is private, supervised, conflict-safe, and controls target hardware. |
| 4 | RFC-005 | ⏳ PLANNED | The user experiences one app across launch, startup, settings, pause, and recovery. |
| 5 | RFC-006 | ⏳ PLANNED | A single compliant installer survives clean install, upgrade, uninstall, and rollback. |

## 17. Features List MoSCoW

| ID | Priority | Feature |
|---|---|---|
| F-001 | Must | One installer, one Start Menu entry, one tray/settings app. |
| F-002 | Must | Bundled pinned OpenRGB 1.0 engine bound to loopback only. |
| F-003 | Must | Internal CPU/GPU sensor bridge with no Core Temp requirement. |
| F-004 | Must | Preserve gradient, EMA, transition, brightness, per-LED CPU/GPU mapping. |
| F-005 | Must | Preserve screensaver pause, lights toggle, sync start/stop, and startup. |
| F-006 | Must | Config v1-to-v2 migration, validation, backup, and atomic save. |
| F-007 | Must | Process ownership, health, bounded restart, conflict handling, and logs. |
| F-008 | Must | PawnIO detection/install/reboot handling for target RAM/mainboard. |
| F-009 | Must | Complete third-party notices, checksums, source obligations, uninstall, rollback. |
| F-010 | Must | Honest support statement tied to bundled OpenRGB detection/support. |
| F-011 | Should | Diagnostics export with versions, statuses, devices, sensor IDs, and redacted paths. |
| F-012 | Should | Explicit legacy-profile reassignment UI when automatic matching is ambiguous. |
| F-013 | Could | Optional user-selectable OpenRGB port after v1 if 6742 conflicts frequently. |
| F-014 | Won't v1 | Vendor SDK plugins, network control, auto-updater, scenes, audio/game sync. |

## 18. RFCs

### RFC-001: Baseline, dependency manifest, and redistribution gate

**Summary:** Establish factual hardware/runtime baseline and lock every binary/package/source/license before implementation.

**Dependencies:** None.

**Stage 0 — Pre-Phase Research**

- Inspect `src/openrgb_tray_app.py`, `src/openrgb_temp_sync.py`, `src/test_openrgb_sync.py`, `config.json`, current build specs, README, and both prior RGB plans.
- Inspect exact OpenRGB 1.0 archive contents without substituting pipeline builds.
- Run the pinned `OpenRGB.exe --help` and record exact safe server/config flags.
- Record existing port 6742 listeners, OpenRGB/Core Temp startup entries, PawnIO state/version, and elevation behavior.
- Enumerate RGB devices/LEDs and LibreHardwareMonitor CPU/GPU sensor candidates on the target machine.
- Confirm openrgb-python 0.3.7 negotiates successfully with SDK protocol 6 and can set/read device data needed by this app.
- Present findings and **STOP** for approval.

**Stages**

1. Add `third_party/dependencies.lock.json` with artifact name, version, source URL, commit/tag, size, digest, license, and source-archive digest.
2. Add hash-locked Python inputs/lock and NuGet lock policy.
3. Add `scripts/fetch-vendor.ps1` that downloads only during build preparation, verifies before extraction, and stages into ignored `vendor/`.
4. Add `third_party/THIRD-PARTY-NOTICES.md` and license/source inventory placeholders populated from exact artifacts.
5. Add a baseline report at `process/general-plans/reports/unified-rgb-baseline_REPORT_19-09-26.md` with hardware/process/port/sensor evidence.

**Files/modules touched**

- Add `third_party/dependencies.lock.json`.
- Add `third_party/THIRD-PARTY-NOTICES.md`.
- Add `requirements.in`, `requirements-dev.in`, `requirements.lock`.
- Add `scripts/fetch-vendor.ps1`.
- Modify `.gitignore` only for generated vendor/build/staging outputs; preserve existing entries.
- Add the baseline report named above.

**Test stage**

- Test file: `tests/test_dependency_manifest.py`.
- Test: required fields, unique artifacts, 64-character SHA-256 values, local staged-file hash verification, prohibited floating versions/URLs.
- Command: `py -3.12 -m unittest discover -s tests -p "test_dependency_manifest.py" -v`.
- Vendor command: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-vendor.ps1 -VerifyOnly`.
- Pass criteria: all manifest tests pass; all staged hashes match; SDK v6 connection and target enumeration succeed; no wildcard listener exists.

**Post-Phase Testing**

- Manual: inspect OpenRGB version/help, launch server loopback-only, enumerate devices, then stop it.
- State: record archive/package hashes, listener PID/path/address, PawnIO status, devices/LEDs, sensors, startup entries.
- Error scenarios: modified archive, unavailable URL, wrong SDK version, missing PawnIO, occupied port.

**Acceptance Criteria**

- Every distributable/build dependency is exact and checksum-locked.
- OpenRGB asset identity matches AD-003.
- openrgb-python SDK v6 behavior is proven on the pinned engine.
- Exact PawnIO and license facts are locked, not guessed.
- Baseline contains the full target hardware matrix.

**Verification Checklist**

- [ ] Automated manifest tests passed.
- [ ] Manual artifact and hardware discovery passed.
- [ ] Port/process/driver state recorded.
- [ ] Failure cases rejected safely.
- [ ] User confirmed baseline.

**What's Functional Now:** Reproducible inputs and factual baseline only; product behavior is unchanged.  
**Ready For:** RFC-002 after user confirmation.

### RFC-002: Python core refactor and config v2 migration

**Summary:** Protect and separate current behavior before adding child-process complexity.

**Dependencies:** RFC-001 `✅ VERIFIED`.

**Stage 0 — Pre-Phase Research**

- Trace every config read/write, map/brightness call, smoothing branch, LED identity lookup, Tk callback, and tray action.
- Capture expected results from the current app for boundary temperatures and representative current config.
- Check working-tree overlap before modifying files.
- Present exact extraction/migration mapping and **STOP** for approval.

**Stages**

1. Create the package/module structure from Section 10 without changing visible behavior.
2. Move pure lighting calculations into `lighting.py`; eliminate duplicate production logic from the old CLI.
3. Implement schema v2 validation, atomic persistence, backup, and legacy migration.
4. Implement stable device/LED profile resolution and unmatched-profile preservation.
5. Convert the tray entrypoint into composition/bootstrap only.
6. Replace stale old-module tests with current production-path tests.

**Files/modules touched**

- Modify `src/openrgb_tray_app.py`.
- Add `src/openrgb_temp_sync/__init__.py`.
- Add `src/openrgb_temp_sync/config.py`.
- Add `src/openrgb_temp_sync/lighting.py`.
- Add `src/openrgb_temp_sync/controller.py` skeleton limited to current behavior.
- Add `src/openrgb_temp_sync/ui.py` from current UI behavior.
- Replace/remove legacy `src/openrgb_temp_sync.py` only after all live entrypoints/scripts are redirected and parity is proven.
- Replace/remove stale `src/test_openrgb_sync.py` after equivalent tests exist under `tests/`.
- Add `tests/test_lighting.py`, `tests/test_config.py`, `tests/fixtures/config-v1-current.json`, and device metadata fixtures.

**Test stage**

- Command: `py -3.12 -m unittest discover -s tests -p "test_*.py" -v`.
- Tests: thresholds, custom colors, brightness 0/10/50/100, clamp behavior, invalid threshold order, EMA sequence, transition speeds 1/5/10, CPU/GPU fallback rules, schema v1 migration, corrupt/oversize config, atomic-write failure, stable matching, ambiguous matching.
- Pass criteria: all tests green; migrated current fixture is semantically identical; production imports without OpenRGB hardware by using injected fakes.

**Post-Phase Testing**

- Manual: run in development against the existing OpenRGB/Core Temp setup only for behavior parity.
- State: diff normalized old and migrated settings; verify backup and original preservation.
- Error: corrupt config and read-only destination produce visible, recoverable outcomes.

**Acceptance Criteria**

- No duplicate gradient/config implementation remains on a live path.
- Current device/LED settings are preserved.
- UI operations are marshaled to Tk's main thread.
- Config saves are atomic and failures are reported.
- Root `config.json` is not modified/deleted by migration.

**Verification Checklist**

- [ ] Python tests passed.
- [ ] Migration diff passed.
- [ ] Manual settings parity passed.
- [ ] Failure handling confirmed.
- [ ] User confirmed settings/behavior.

**What's Functional Now:** Existing product behavior on a testable core with safe config migration.  
**Ready For:** RFC-003.

### RFC-003: LibreHardwareMonitor sensor bridge

**Summary:** Replace Core Temp and direct NVML with one internal, versioned sensor stream.

**Dependencies:** RFC-001 and RFC-002 `✅ VERIFIED`.

**Stage 0 — Pre-Phase Research**

- Re-enumerate live LibreHardwareMonitor sensors under the same elevation level planned for release.
- Confirm exact .NET 8 SDK/runtime patch, NuGet lock, self-contained publish output, and LibreHardwareMonitor notices.
- Confirm target CPU/GPU selector names/identifiers and permission behavior.
- Present sensor selection/elevation findings and **STOP** for approval.

**Stages**

1. Implement sensor models, deterministic selector, hello/sample/fatal serialization, and exit codes.
2. Keep the LibreHardwareMonitor computer open; update CPU/GPU only at one-second intervals.
3. Add bridge unit tests for selection, null values, ambiguity, serialization, and monotonic sequence.
4. Implement Python helper launch, protocol validation, stale detection, logs, bounded restart, and status snapshot.
5. Remove Core Temp mmap and direct NVML from live production paths after parity is proven.
6. Add build/publish script and stage the self-contained helper.

**Files/modules touched**

- Add the four sensor-bridge files in Section 10.
- Add `sensor-bridge/tests/OpenRGBTempSync.SensorBridge.Tests.csproj` and selector/protocol tests.
- Add `src/openrgb_temp_sync/sensor_runtime.py`.
- Add `tests/test_sensor_runtime.py` and NDJSON fixtures.
- Modify `src/openrgb_tray_app.py`, `src/openrgb_temp_sync/controller.py`, `src/openrgb_temp_sync/ui.py`.
- Add `scripts/build-sensor-bridge.ps1`.
- Modify NuGet lock and dependency/notice files.

**Test stage**

- Command: `dotnet test sensor-bridge/tests/OpenRGBTempSync.SensorBridge.Tests.csproj --configuration Release --locked-mode`.
- Command: `py -3.12 -m unittest tests.test_sensor_runtime -v`.
- Command: published helper probe mode, once elevated and once non-elevated, with output captured.
- Pass criteria: deterministic selectors pass; valid stream accepted; malformed/stale/oversize stream rejected; owned crash restarts are bounded; live CPU/GPU samples update.

**Post-Phase Testing**

- Manual: close Core Temp completely, exercise idle CPU, CPU load, GPU load, and source switching.
- Verification: compare five-minute sampled values to a trusted independent tool; target median absolute difference ≤5 °C and no implausible spikes outside validation range.
- Error: missing permissions, no sensor, helper crash, stdout close, malformed line, stale samples.

**Acceptance Criteria**

- Core Temp and direct NVML are absent from live code.
- Helper is self-contained and hidden.
- Sensor selection is deterministic and reported.
- Null/stale data never masquerades as a cool temperature.
- CPU/GPU mappings still drive the intended LEDs.

**Verification Checklist**

- [ ] .NET tests passed.
- [ ] Python protocol tests passed.
- [ ] Live comparison passed.
- [ ] Failure/restart handling confirmed.
- [ ] User confirmed operation with Core Temp closed.

**What's Functional Now:** Self-contained CPU/GPU sensing.  
**Ready For:** RFC-004.

### RFC-004: OpenRGB engine lifecycle and safe connection

**Summary:** Make OpenRGB an internal managed dependency with strict loopback and ownership rules.

**Dependencies:** RFC-001 through RFC-003 `✅ VERIFIED`.

**Stage 0 — Pre-Phase Research**

- Reconfirm exact command flags from staged binary.
- Inspect Windows listener/PID APIs and choose the minimum stdlib/ctypes implementation.
- Reconfirm SDK v6 negotiation and target device metadata exposed by openrgb-python.
- Inspect PawnIO initialization logs and startup scan time after reboot.
- Present process/state machine details and **STOP** for approval.

**Stages**

1. Implement listener inspection and conflict classification.
2. Implement verified bundled launch with hidden window, dedicated config/log directory, and loopback flags.
3. Implement compatibility handshake, device enumeration, Direct mode negotiation, and owned/external distinction.
4. Implement Job Object attachment, graceful stop, health checks, reconnect, and restart budget.
5. Integrate device profile resolution and current LED loop.
6. Add conflict/recovery UI statuses and diagnostics.

**Files/modules touched**

- Add `src/openrgb_temp_sync/openrgb_runtime.py`.
- Add `src/openrgb_temp_sync/windows_runtime.py` for minimal Win32 process/port/job wrappers.
- Modify controller, UI, entrypoint, spec, dependency manifest, and notices.
- Add `tests/test_openrgb_runtime.py`, `tests/test_controller.py`, and fake SDK/process fixtures.

**Test stage**

- Command: full Python unit suite.
- Integration harness cases: free port; valid bundled engine; compatible external engine; unrelated listener; wildcard OpenRGB listener; incompatible protocol; delayed readiness; no devices; child crash; SDK disconnect; retry-budget exhaustion; app exit.
- Pass criteria: expected state for every case; no external termination; no orphan owned child; no non-loopback bind.

**Post-Phase Testing**

- Manual: run without a manually opened OpenRGB UI; inspect tray, process tree, port, devices, per-LED response, engine kill/restart, and exit.
- State commands: `Get-NetTCPConnection -LocalPort 6742`, listener PID/path inspection, Task Manager/Process Explorer child tree, OpenRGB logs.
- Error: competing vendor RGB apps, PawnIO missing, port conflict, slow scan, device disconnect.

**Acceptance Criteria**

- Default runtime launches bundled OpenRGB invisibly.
- Port is loopback-only.
- Safe compatible external reuse works and is labeled.
- Unsafe/incompatible listeners block without being killed.
- Owned children stop on normal exit and parent crash.
- Target mainboard, RAM, and GPU controller are detected and controllable.

**Verification Checklist**

- [ ] Unit/integration tests passed.
- [ ] Loopback/process evidence recorded.
- [ ] Hardware control matrix passed for engine layer.
- [ ] Conflict/crash handling confirmed.
- [ ] User confirmed no manual OpenRGB step.

**What's Functional Now:** Managed private RGB engine plus internal sensing.  
**Ready For:** RFC-005.

### RFC-005: One-app UX, startup, and diagnostics

**Summary:** Complete the visible experience and Windows startup behavior without adding a second management surface.

**Dependencies:** RFC-001 through RFC-004 `✅ VERIFIED`.

**Stage 0 — Pre-Phase Research**

- Inspect current tray/settings threading, startup registry state, pystray shutdown behavior, and frozen-path logic.
- Confirm Scheduled Task commands and behavior for the current user and elevated executable.
- Confirm named mutex/event behavior across the elevated per-user session.
- Present exact UX/status/startup migration behavior and **STOP** for approval.

**Stages**

1. Add single-instance mutex and show-settings activation event scoped to the current user/session.
2. Replace registry startup management with one named Scheduled Task at logon/highest privilege.
3. Migrate/remove only the product's legacy `OpenRGBTempSync` Run value after task creation succeeds.
4. Preserve and wire all tray/settings controls to the new controller snapshots.
5. Add engine/sensor/device/error status and redacted diagnostics export.
6. Ensure lights-off, screensaver pause, stop/start, and exit semantics are deterministic.

**Files/modules touched**

- Modify `src/openrgb_temp_sync/windows_runtime.py`, controller, UI, config, and entrypoint.
- Add `tests/test_windows_runtime.py` for command construction/state mapping using fakes; live Scheduled Task behavior remains a manual Windows integration gate.
- Modify README for one-app instructions and troubleshooting.

**Test stage**

- Command: full Python unit suite.
- Manual Windows cases: cold launch, second launch, enable startup, logoff/logon, disable startup, task failure, settings save/reopen, screensaver, lights off/on, sensor/engine degraded state, Retry, diagnostics export, exit.
- Pass criteria: one instance, one icon, one task, settings preserved, main thread remains responsive, no orphan child.

**Post-Phase Testing**

- State: inspect task XML/action/run level; confirm legacy Run value handling; count tray icons/processes; verify LocalAppData files.
- Error: task creation denied, activation event missing, UI opened during scan, config save failure.

**Acceptance Criteria**

- Start Menu entry starts or activates the same product.
- One tray icon/settings UI manages everything.
- Startup works after reboot without a UAC prompt at logon.
- Startup disable removes only the product task.
- Existing UI controls and behaviors remain functional.
- Diagnostics omit full config and unnecessary personal data.

**Verification Checklist**

- [ ] Automated tests passed.
- [ ] Launch/startup/reboot workflow passed.
- [ ] One-instance/icon/task state confirmed.
- [ ] Degraded/recovery UX confirmed.
- [ ] User confirmed one-app workflow.

**What's Functional Now:** Complete one-app runtime experience from source/dev build.  
**Ready For:** RFC-006.

### RFC-006: Installer, release verification, uninstall, and rollback

**Summary:** Produce and validate the single distributable installer and complete legal/operational closeout.

**Dependencies:** RFC-001 through RFC-005 `✅ VERIFIED`.

**Stage 0 — Pre-Phase Research**

- Inspect the completed runtime dependency tree and generated payload.
- Verify exact PawnIO unattended/install/reboot/uninstall behavior from the pinned signed artifact.
- Confirm Inno compiler version, AppId, install paths, upgrade semantics, code-signing availability, Defender behavior, and source-notice completeness.
- Present final installer actions and rollback plan and **STOP** for approval.

**Stages**

1. Finalize PyInstaller onedir spec with elevation manifest, icon, version metadata, hidden imports, and no web-simulator payload.
2. Build self-contained bridge and verified vendor/legal/source staging.
3. Implement Inno Setup install, upgrade, task, PawnIO, reboot, uninstall, and retention choices.
4. Add release verifier for versions, hashes, forbidden files, port safety, process cleanup, notices, and source archives.
5. Build release candidate and execute clean/upgrade/uninstall/rollback matrices.
6. Run final code/security/license review and create the high-risk evidence pack.

**Files/modules touched**

- Modify `OpenRGBTempSync.spec`; retire the debug spec from release use.
- Add/modify all build/installer scripts from Section 10.
- Add `installer/OpenRGBTempSync.iss` and installer assets.
- Finalize dependency lock, notices, `licenses/`, and `sources/` staging rules.
- Modify README and add `docs/BUILD.md`, `docs/TROUBLESHOOTING.md`, `docs/THIRD_PARTY.md`.
- Add `tests/test_installed_layout.py` and release verification fixtures.
- Do not include or modify Newton simulator runtime files.

**Test stage**

- Unit: full Python and .NET suites.
- Build: sensor publish, PyInstaller onedir, Inno compile, release verifier.
- Fresh install: Windows 11 x64 without external OpenRGB/Core Temp.
- Upgrade: legacy executable/config and prior release candidate.
- Uninstall: retain settings default, remove-settings choice, PawnIO retain/remove choice when eligible.
- Rollback: failed upgrade and manual reinstall of previous installer/config backup.
- Pass criteria: all checks green, hardware matrix green, evidence pack complete, user accepts release candidate.

**Post-Phase Testing**

- Manual: installer UI, elevation explanation, reboot-required flow, Start Menu/tray, Programs and Features, settings preservation, uninstall cleanup, previous-version restore.
- State: installed file hashes, task, processes, port, LocalAppData, PawnIO ownership marker, license/source tree.
- Error: tampered dependency, missing driver, install cancellation, locked file, failed child start, failed task creation, uninstall while running.

**Acceptance Criteria**

- One installer is sufficient on the target PC.
- Installer performs no unverified runtime download.
- One visible app works after reboot.
- Uninstall cleans owned artifacts and preserves shared/user data by default.
- Rollback restores a working previous version and config.
- All legal/source/checksum obligations are present.
- Final user confirmation and review decision are recorded.

**Verification Checklist**

- [ ] Full automated suites passed.
- [ ] Clean/upgrade/uninstall/rollback tests passed.
- [ ] Hardware/manual matrix passed.
- [ ] Security/license review passed.
- [ ] Evidence pack complete.
- [ ] User confirmed release candidate.

**What's Functional Now:** Installable, supportable one-app product.  
**Ready For:** UPDATE PROCESS closeout and archival only after user confirmation.

## 19. Test Strategy

### Automated layers

1. **Pure Python unit tests:** lighting math, smoothing, config, identity matching, protocol parsing, state transitions, command construction.
2. **.NET unit tests:** sensor selection, serialization, null/ambiguity handling, exit classifications.
3. **Process integration tests:** fake helper, fake listener, real pinned OpenRGB in controlled modes, child ownership/restart/cleanup.
4. **Build verification:** dependency hashes, locked restores, output inventory, embedded version metadata, forbidden payload scan.
5. **Installed-layout tests:** expected files/notices/sources, writable-path separation, task/shortcut/uninstall registration.

### Commands to establish during execution

- Python: `py -3.12 -m unittest discover -s tests -p "test_*.py" -v`.
- .NET: `dotnet test sensor-bridge/tests/OpenRGBTempSync.SensorBridge.Tests.csproj --configuration Release --locked-mode`.
- Vendor: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-vendor.ps1 -VerifyOnly`.
- Build: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-installer.ps1`.
- Release: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-release.ps1 -Installer <candidate>`.

The existing `npm run test` is for the unrelated Newton simulator. Run it only as a narrow regression check if shared root files such as `package.json` or `.gitignore` change; it is not evidence that the RGB product works.

### Test data rules

- Use anonymized fixtures derived from device metadata, not the live user config.
- Keep a checked-in legacy v1 fixture representing all supported fields.
- Do not require physical RGB hardware for unit tests.
- Hardware integration tests are explicitly non-CI and must be recorded on the target PC.

## 20. Failure Modes and Required Behavior

| Failure | Required behavior |
|---|---|
| Port 6742 free but engine fails | Retry with bounded backoff, enter degraded state, retain logs, offer Retry. |
| Port occupied by unrelated process | Do not connect/kill; show PID/image/bind-safe remediation. |
| OpenRGB bound to wildcard/LAN | Refuse connection; instruct user to stop/reconfigure it. |
| Compatible external OpenRGB | Reuse, label external, never terminate it. |
| PawnIO absent/denied | Distinguish from zero devices; installer repair guidance; no infinite scanning. |
| OpenRGB detects zero devices | Keep app available, show zero devices and logs, allow Retry after conflict apps close. |
| Sensor helper missing/tampered | Refuse launch based on manifest; degraded sensor state. |
| CPU or GPU sensor missing | Null only that source; show selected/available metadata; affected LEDs stop updating after grace. |
| Malformed/stale helper data | Reject, log bounded detail, restart within budget, never fake temperature. |
| Config corrupt | Backup/quarantine, defaults, visible warning, no data deletion. |
| Config save fails | Keep old persisted state, report failure, do not close as if saved. |
| Device renamed/reordered | Stable match or preserve as unmatched; never silently attach ambiguous profile. |
| Child crashes repeatedly | Stop after three restarts/60 seconds; manual Retry required. |
| App crashes | Job Object kills owned children; external server survives. |
| Screensaver query fails | Continue normal lighting and log once; do not unexpectedly black out. |
| Startup task creation fails | Leave prior startup mechanism until new task succeeds; show error. |
| Upgrade fails | Restore prior install/config pointer; leave diagnostic log. |
| Uninstall while app runs | Stop owned product tree, never kill external OpenRGB. |
| Reboot required for driver | Persist pending state and resume verification after reboot. |

## 21. Manual Hardware Matrix

| Surface | Expected baseline | Tests | Green evidence |
|---|---|---|---|
| Ryzen 7 5800X sensor | `Core (Tctl/Tdie)` preferred | Idle, CPU load, helper restart, Core Temp closed | Non-null 1 Hz samples, stable source ID, within ≤5 °C median difference. |
| RTX 3060 sensor | `GPU Core` preferred | Idle, GPU load, source switch | Non-null samples and visible LED color response. |
| ENE DRAM | 8 reported LEDs in current config | Direct mode, CPU source, 10% brightness, per-LED persistence | All reported LEDs controllable; two DIMMs remain detected after reboot. |
| Gigabyte AORUS RTX 3060 ELITE LHR | 5 zones | GPU source, 0/10/100% brightness, reconnect | Correct zones respond to GPU temperature and persist. |
| MSI MAG B550 TOMAHAWK | JRGB1, JRGB2, JRAINBOW1 LEDs, onboard LEDs | Mixed CPU/GPU source, 0/50/100%, screensaver | Correct zones respond; disabled LEDs remain off; restore after screensaver. |
| OpenRGB engine | 1.0 / SDK 6 | Cold start, external reuse, kill/restart, port conflict | Loopback-only, no GUI/tray, no orphan. |
| Startup | One highest-privilege per-user task | Enable, reboot/logon, disable | One icon and healthy process tree without manual launch. |
| Installer | One x64 installer | Fresh, upgrade, repair, cancel | Correct files/tasks/notices and config migration. |
| Uninstaller | Product cleanup | Keep config, remove config, PawnIO choices | Owned artifacts removed; shared/external state preserved. |

The target device names/counts are baseline expectations, not a universal contract. If OpenRGB 1.0 reports different names or counts, record the difference and require explicit user confirmation before updating this plan.

## 22. Acceptance Criteria Version 1.0

- [ ] A clean Windows 11 x64 target needs only the one product installer.
- [ ] The product creates one Start Menu entry and one tray icon.
- [ ] Normal operation requires no manual OpenRGB/Core Temp action.
- [ ] Bundled OpenRGB is exactly the pinned stable 1.0 artifact and binds only to `127.0.0.1:6742`.
- [ ] Compatible external server reuse passes all safety checks; unsafe listeners are refused.
- [ ] Ryzen 7 5800X and RTX 3060 temperature readings pass live comparison.
- [ ] Mainboard, RAM, and GPU RGB devices pass the manual matrix.
- [ ] Gradient, EMA, transitions, brightness, per-LED source, screensaver, lights, and startup behaviors are preserved.
- [ ] Existing config migrates losslessly, with backup and no original deletion.
- [ ] Crashes/conflicts/missing prerequisites produce actionable status and bounded recovery.
- [ ] Owned child processes never remain after parent exit/uninstall.
- [ ] Installer upgrade/uninstall/rollback matrices pass.
- [ ] Dependency versions/hashes, licenses, third-party notices, and corresponding source are complete.
- [ ] Support wording says “devices supported and detected by the bundled OpenRGB engine,” not “all devices.”
- [ ] All automated suites, release verification, security review, evidence pack, and user confirmation are complete.

## Touchpoints

### Modify

- `src/openrgb_tray_app.py` — bootstrap/composition and shutdown only.
- `OpenRGBTempSync.spec` — onedir release bundle, elevation/version metadata, internal assets.
- `OpenRGBTempSync_Debug.spec` — either align for developer diagnostics or retire from documented release paths.
- `README.md` — one-app install/use/troubleshooting/support claim.
- `.gitignore` — generated vendor, build, release, logs, LocalAppData fixtures if needed.
- `start.bat`, `stop.bat` — retire from end-user workflow; keep developer-safe wrappers only if still useful.
- `package.json` — only if stale Python scripts are removed; do not mix the web simulator into release tooling.
- `process/general-plans/active/rgb_brightness_config_PLAN_31-05-26.md` — do not rewrite during EXECUTE; reference as predecessor and reconcile/archive later through UPDATE PROCESS.

### Add

- Python package files listed in Section 10.
- Sensor bridge and its tests.
- `tests/` Python test suite and fixtures.
- Build/vendor/installer scripts listed in Section 10.
- `requirements.in`, `requirements-dev.in`, `requirements.lock`.
- `third_party/dependencies.lock.json`, notices, staged license/source rules.
- `docs/BUILD.md`, `docs/TROUBLESHOOTING.md`, `docs/THIRD_PARTY.md`.
- RFC reports and high-risk evidence pack under `process/general-plans/reports/`.

### Retire after parity proof

- Live reliance on `src/openrgb_temp_sync.py`.
- Stale `src/test_openrgb_sync.py` test location.
- Core Temp mmap code.
- Direct NVML ctypes code.
- Legacy HKCU Run startup path.
- Onefile root/dist executable as release artifact.

### Preserve/out of runtime scope

- `config.json` as user migration input until user confirms installed migration; never delete automatically.
- `index.html`, `src/main.js`, `src/style.css`, `src/physics.test.js`, `vite.config.js`, and web simulator assets.
- Unrelated dirty `.agents`/workspace changes.

## Public Contracts

### User-facing contracts

- Product name remains **OpenRGB Temp Sync** unless the user explicitly approves a rename.
- One installer, one Start Menu entry, one tray icon/settings window.
- Existing tray actions remain: status, start/stop sync, lights on/off, Settings, startup toggle, Exit.
- Existing settings remain: low/mid/high thresholds/colors, transition speed, screensaver pause, device/LED brightness, CPU/GPU source.
- Device support statement is limited to bundled OpenRGB-supported and detected hardware.

### On-disk contracts

- Install root: `%ProgramFiles%\OpenRGB Temp Sync\`.
- User state: `%LOCALAPPDATA%\OpenRGBTempSync\`.
- Config schema: v2 as Section 12.
- Logs: capped/rotated, no unbounded growth.
- Installer registers one Programs and Features entry and one Start Menu shortcut.
- Startup task has one stable product-owned name and absolute quoted action.

### Network/process contracts

- OpenRGB SDK host/port: `127.0.0.1:6742` only for v1.
- SDK compatibility: negotiated protocol 5 or 6; bundled target is 6.
- Sensor IPC: version 1 NDJSON over child stdout; no listening endpoint.
- External OpenRGB is never owned/killed.
- Owned children are inside kill-on-close Job Object.

### Compatibility contracts

- Legacy v1 config values migrate or remain explicitly unmatched; none are silently discarded.
- openrgb-python 0.3.7 behavior with OpenRGB SDK 6 must be proven before implementation proceeds.
- Future additive NDJSON fields are ignored; schema-version changes are rejected until supported.
- No vendor plugin API is promised.

## Blast Radius

### High risk

- Elevated runtime and Scheduled Task.
- PawnIO driver installation/reboot.
- OpenRGB SDK network listener and historical remote-exposure risk.
- Per-LED writes to SMBus/I2C-backed controllers.
- Installer upgrade/uninstall and config migration.
- GPL/MPL redistribution obligations.

### Medium risk

- Tkinter/pystray cross-thread behavior.
- Child process restart and shutdown.
- Device identity changes across OpenRGB upgrade.
- Sensor selection/accuracy.
- PyInstaller frozen resource paths and antivirus behavior.

### Low risk

- Pure gradient/brightness calculations once covered by tests.
- Documentation and diagnostics formatting.

### Systems intentionally unaffected

- Newton simulator behavior/build/deployment.
- User's vendor RGB apps except conflict detection/advice.
- External OpenRGB installation/configuration.
- Non-lighting sensors/controls.
- Network firewall configuration.

## Verification Evidence

### Required per RFC report

Store reports under `process/general-plans/reports/` and include:

- selected plan/RFC and commit/worktree identity;
- exact commands and exit codes;
- automated test counts/results;
- file/artifact hashes;
- process tree and port binding evidence where relevant;
- device/sensor enumeration with bounded metadata;
- screenshots for tray/settings/installer states;
- config migration normalized diff without sensitive full content;
- error cases exercised and observed result;
- user manual steps and confirmation;
- deviations and plan updates.

### Final release evidence

- `dependencies.lock.json` and verified artifact hash output.
- Python and .NET test reports.
- Build/installer/release-verifier logs.
- Installed file inventory/hashes.
- `Get-NetTCPConnection` loopback evidence.
- Process ownership/orphan checks.
- Scheduled Task XML/state.
- PawnIO state and reboot result.
- Hardware matrix results.
- Clean install/upgrade/uninstall/rollback results.
- License/source inventory audit.
- High-risk harness pack and reviewer decision.
- Explicit user confirmation.

### What green does not prove

- Compatibility with hardware not present in the target matrix.
- Support for devices OpenRGB does not support/detect.
- Safety of enabling LAN SDK access; LAN access remains unsupported.
- Correctness of future OpenRGB, Python, .NET, or driver versions not in the lock.

## Resume and Execution Handoff

### Primary execute anchor

`process/general-plans/active/unified_rgb_desktop_app_PLAN_19-09-26.md`

### Read first on every resumed execution

1. This plan, especially current phase table and selected RFC.
2. `process/context/all-context.md`.
3. `process/context/tests/all-tests.md` while remembering it documents the web simulator, so this plan's Python/.NET commands govern RGB work.
4. Latest report for the selected RFC under `process/general-plans/reports/`.
5. `git status --short` and recent diff to preserve user changes.
6. `third_party/dependencies.lock.json` after RFC-001 exists.

### Execution rules

- Select exactly one RFC.
- Perform that RFC's Stage 0 research and stop for approval before source implementation.
- Do not hand an agent the whole plan as one implementation request.
- Update status only with evidence; code existence is `🔨 CODE DONE`, not `✅ VERIFIED`.
- If repo/hardware truth invalidates an architecture decision, return to PLAN and use Change Management below.
- After each verified RFC, create its report before moving on.
- Before RFC-006 completion, run tester, correctness review, security review, and license audit.

### Exact first execution step

Enter EXECUTE with **RFC-001 only**. The first action is read-only: compute and record the current `git status`, legacy `config.json` SHA-256, port-6742 listener/PID/bind address, OpenRGB/Core Temp startup/process state, PawnIO version/state, and current RGB device/LED enumeration. Then inspect the pinned OpenRGB 1.0 archive/help output and present the baseline findings to the user. **Stop before creating or modifying any source/dependency file until the user approves those findings.**

### Blocker rules

Mark the selected RFC `🚧 BLOCKED` only for a real stop condition such as unavailable pinned artifact/source, failed SDK v6 compatibility, unsafe unavoidable listener binding, unresolvable driver install, absent target sensor, or inability to preserve legacy config. Record evidence and safest next action; do not widen scope to vendor SDKs automatically.

## 28. Implementation Checklist

1. [ ] RFC-001: capture baseline state and user confirmation before edits.
2. [ ] Lock OpenRGB 1.0, openrgb-python 0.3.7, LibreHardwareMonitorLib 0.9.6, runtimes/tools, PawnIO, hashes, licenses, and source archives.
3. [ ] Add vendor acquisition/manifest tests and verify rejection of a tampered artifact.
4. [ ] RFC-002: extract pure lighting/config logic and add current-path Python tests.
5. [ ] Implement/configure schema v2 migration, backup, atomic save, stable matching, and unmatched preservation; prove current config parity.
6. [ ] Refactor entrypoint/UI/controller without behavior loss and retire stale duplicate paths only after tests/manual parity.
7. [ ] RFC-003: implement/test/publish the .NET sensor bridge and NDJSON contract.
8. [ ] Integrate/test helper supervision, stale/error handling, and remove Core Temp/NVML from live paths after live comparison.
9. [ ] RFC-004: implement/test loopback listener inspection, compatible external reuse, verified bundled launch, SDK handshake, Job Object, restart budget, and shutdown.
10. [ ] Pass target OpenRGB device/LED control and conflict/crash integration gates.
11. [ ] RFC-005: implement/test single instance, activation, one tray/settings UX, scheduled startup migration, runtime status, and diagnostics.
12. [ ] Pass reboot/startup/screensaver/lights/settings/degraded/retry/manual workflows.
13. [ ] RFC-006: build self-contained helper, PyInstaller onedir app, legal/source tree, and Inno Setup installer from verified inputs.
14. [ ] Pass clean install, legacy upgrade, repair, cancel, reboot-required, uninstall-retain, uninstall-clean, and rollback tests.
15. [ ] Run full automated suites, release verifier, security/license review, and manual hardware matrix.
16. [ ] Create high-risk evidence pack, obtain user release-candidate confirmation, then route to UPDATE PROCESS for reconciliation/archival.

## 29. Risks and Mitigations

| Risk | Likelihood/Impact | Mitigation |
|---|---|---|
| OpenRGB 1.0 changes device names/counts | Medium/High | Baseline before migration; stable metadata/signature match; preserve unmatched profiles. |
| openrgb-python 0.3.7 lacks required SDK 6 behavior | Medium/High | RFC-001 protocol proof gate; if it fails, return to PLAN rather than patch protocol ad hoc. |
| PawnIO install/reboot timing hides RAM/mainboard | Medium/High | Explicit driver state, delayed post-logon scan/retry, reboot gate, separate status. |
| Elevated startup creates UAC/task friction | Medium/Medium | Installer-created highest-privilege per-user task; manual cold launch disclosure; no custom service. |
| Competing RGB apps lock buses/devices | High/High | Detect/log conflict, advise close/disable, no forced termination. |
| Sensor values differ from expected names | Medium/Medium | Identifier persistence, strict ordered names, no ambiguous guessing, diagnostic enumeration. |
| PyInstaller/unsigned binaries trigger Defender | Medium/High | Onedir, code sign when available, version metadata, reproducible hashes, manual Defender test. |
| GPL/MPL non-compliance | Medium/High | Ship licenses/corresponding source; audit before release; legal block if app license incompatible. |
| Orphaned children after crash | Low/High | Kill-on-close Job Object and orphan tests. |
| Config loss on upgrade | Low/High | Never edit legacy input; backups, atomic write, rollback test. |
| Unsafe SDK exposure | Low/Critical | Explicit loopback flag, listener verification, refusal of wildcard, no firewall rule. |

## 30. Operations Runbook

### Normal status checks

- Tray status should be `Running` with owned/external engine label and fresh CPU/GPU readings.
- Port 6742 must show only loopback.
- OpenRGB and sensor helper should be descendants/job members of the app when owned.
- Logs should identify versions, selected sensors, device count, and last health transition.

### User remediation order

1. Use tray `Retry`.
2. Open diagnostics/status for exact engine/sensor/driver conflict.
3. Close competing RGB/hardware monitor tools if indicated.
4. Run installer Repair for missing/tampered payload or PawnIO.
5. Reboot if driver state says pending.
6. Roll back to prior installer/config backup if an upgrade introduced regression.

### Support bundle

Export only app/OpenRGB/helper versions, manifest status, redacted paths, engine ownership/bind, device/LED names/counts, sensor IDs/names/health, recent bounded logs, and config schema/validation summary. Do not export the entire user config by default.

## 31. Change Management

When facts change, classify the change:

- **New/Modify/Remove:** feature or contract change.
- **Scope:** target hardware/OS or one-app definition changed.
- **Technical:** pinned artifact/protocol/driver/runtime differs.
- **Timeline:** an RFC must split or defer.

Required response:

1. Identify affected RFCs, contracts, tests, licenses, installer, migration, and rollback.
2. Decide immediate plan update, scheduled follow-up, or deferral.
3. Update this plan before implementation continues.
4. Communicate impact and obtain approval.

Automatic return to PLAN is required if:

- openrgb-python cannot safely support SDK 6;
- the target hardware cannot be detected with the pinned engine/PawnIO;
- sensor bridge cannot read required CPU/GPU data under the approved privilege model;
- one elevated process tree proves infeasible and a service split is proposed;
- redistribution terms require a different application licensing/distribution model;
- config migration cannot be lossless.

## 32. Verification Comprehensive Review

### Gap analysis before execution

- Repo context documentation currently describes the Newton simulator rather than the RGB runtime; this plan is the authoritative RGB execution context until UPDATE PROCESS reconciles it.
- Python runtime dependencies are not installed in the current Python 3.12 environment.
- .NET SDK is not currently available on PATH.
- Current RGB tests target the old CLI module.
- Existing binaries/specs are onefile and do not include OpenRGB/helper/legal payloads.
- Current code silently swallows many failures and writes logs/config beside the executable.
- Exact PawnIO package metadata must be locked from the OpenRGB 1.0 release payload during RFC-001.

### Quality assessment target

| Dimension | Target | Reason |
|---|---|---|
| Product completeness | 9/10 | Covers install through rollback; universal hardware support intentionally excluded. |
| Architecture clarity | 9/10 | Three-process internals with one visible owner and explicit contracts. |
| Security | 9/10 | Loopback/process validation, pipes, elevation boundaries, hashes, high-risk evidence. |
| Testability | 9/10 | Pure logic split, protocol fixtures, process harness, hardware matrix. |
| Maintainability | 8/10 | Keeps Python UI but splits the monolith; two language toolchains are necessary for sensors. |
| Licensing readiness | 9/10 | Explicit source/notices audit and release block. |

## 33. Future Work

Deferred until v1 evidence proves a need:

- Additional temperature sources or user-selectable sensor picker.
- Vendor-specific RGB backends for hardware OpenRGB does not support.
- Auto-update with signed metadata and rollback.
- Optional port configuration.
- Non-admin UI plus privileged service split.
- Profiles/scenes, schedules, audio/game integrations, remote control.
- Automated hardware-in-loop rig beyond the current PC.

## 34. Cursor Plan and RIPER-5 Guidance

- **Cursor Plan mode:** import Section 28, select one RFC at a time, and stop at each verification/user-confirmation gate.
- **RIPER-5:** this PLAN is complete; implementation requires explicit `ENTER EXECUTE MODE` with RFC-001 selected.
- Reattach this exact plan in future sessions.
- If scope changes, update Change Management before code.
- After each RFC, keep status honest and write durable evidence.
- After final verified release, route through UPDATE PROCESS for context reconciliation and plan archival.

**Next Step:** Say `ENTER EXECUTE MODE for RFC-001 using process/general-plans/active/unified_rgb_desktop_app_PLAN_19-09-26.md` to begin the read-only baseline and dependency-lock gate. Each RFC must be verified and user-confirmed before the next begins.
