# Phase 03 Report — Device Effects, Thermal Ownership, and App Profiles

**Date**: 20-09-2026
**Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (automated mode/thermal/profile contracts pass; live MSI effect readback rejected and cold-boot/user confirmation remain pending)
**Depends on**: Phase 02 Verified

## Executive Summary
Phase 03 implements capability-driven device lighting modes and parameters, integrates independent per-device control ownership (simultaneous GPU hardware effect + MSI thermal sync + RAM manual color), isolates sensor degradation and missing sensor channels without cross-remapping, and introduces persistent application profiles with atomic disk persistence.

All device mode and color writes route strictly through serialized `OpenRGBSupervisor` methods (`set_mode`, `set_colors`, `save_device_mode`, `restore_device`) using stable descriptor keys; no direct SDK object writes are performed from UI components or sensor loops.

## Touchpoints and Changed Files
1. `src/openrgb_temp_sync/openrgb_runtime.py`:
   - Normalized `ModeDescriptor`: added properties `supports_speed`, `supports_brightness`, `supports_direction`, `supports_per_led`, `supports_mode_specific_color`, `supports_random_color`, `supports_manual_save`, `supports_automatic_save`, `supports_save`, as well as parameter range metadata (`speed_min/max`, `brightness_min/max`, `colors_min/max`, `direction`, `directions_supported`).
   - Added `normalize_mode_descriptor` adapter converting SDK ModeData/Mock modes safely into immutable `ModeDescriptor` records; protocol mismatches or missing attributes degrade gracefully to unsupported without raising or blindly bumping protocol versions.
   - Enhanced `WriteResult` with truthy `__bool__` protocol for convenient boolean checks while preserving structured error codes and messages.
   - Added serialized `OpenRGBSupervisor.set_mode(target_key, mode, speed, brightness, direction, colors, save)` executing under `_sdk_lock`, checking capability gates, validating ranges, and verifying active mode readback.
   - Added `OpenRGBSupervisor.save_device_mode(target_key)` gated strictly on mode save advertising (`supports_save`).
   - Preserved existing `restore_device` as in-memory pre-sync baseline snapshot restoration; no manufacturer factory reset claim.
2. `src/openrgb_temp_sync/controller.py`:
   - Enforced canonical target identity (`DeviceDescriptor.stable_key` / `key`) across `_device_owners`, `_manual_reset_devices`, and per-LED color cache prefixes.
   - Added `resolve_target_key(target)` compatibility resolver supporting canonical descriptor keys, UI tree display labels, and unique legacy display names while strictly rejecting ambiguous duplicate names.
   - Updated `set_device_hardware_mode(target_key, mode_name, ...)` to preserve canonical key identity without demoting to duplicate display names.
   - Updated `reset_device_to_original(target)` and `resume_device(target)` to operate strictly on canonical target keys; ambiguous targets are safely rejected.
   - Updated `_send_black_to_all` and `_dispatch_thermal_frame` to gate on `target_key` canonical ownership rather than raw display names.
   - Resume-to-thermal now uses OpenRGB's dedicated custom-mode negotiation when the SDK exposes it, which is required for MSI hardware-effect -> Direct transitions; active-mode readback is verified before the transition is accepted.
   - Quiescing thermal frames: `can_apply_thermal_frame` strictly gates on `owner == "thermal_direct"`; devices assigned to `hardware_mode` or `manual_direct` receive zero thermal writes.
   - Decoupled sensor temperature mapping:
     - Missing GPU sensor does NOT silently remap to CPU temperature.
     - Missing CPU sensor does NOT block GPU-targeted thermal sync.
     - Stale or offline sensor marks controller `DEGRADED_SENSOR` and pauses thermal loop writes without modifying or clearing manual color or hardware effect targets.
   - Hardened `_apply_saved_zone_sizes()`: counts same-name descriptors across active inventory; legacy display-name zone count fallback is strictly gated on name uniqueness (`name_counts == 1`), ensuring duplicate physical hardware sharing identical display names (e.g. dual ENE DRAM modules with strong stable identities) never inadvertently inherit ambiguous legacy profile zone sizes while canonical stable-key configurations remain preferred.
3. `src/openrgb_temp_sync/config.py`:
   - Updated `DEFAULT_CONFIG_V2` and `validate_config_v2` with `profiles` dictionary and `active_profile` tracking.
   - Added `ConfigManager.save_profile(name, profile_data)` with atomic file replacement and timestamped backup creation.
   - Added `ConfigManager.load_profile(name)`, `list_profiles()`, and `delete_profile(name)`.
   - Added `ConfigManager.apply_profile(name, controller)`: safely updates active configuration and controller device owners while explicitly preserving devices currently held in reset or marked unmanaged.
   - Maintained full backwards compatibility with schema v2 and lossless v1 legacy migration.
4. `src/openrgb_temp_sync/ui_model.py`:
   - Added `UIModel.get_mode_capabilities(mode)` summarizing capability gates and human-readable disable reasons for UI controls.
   - Added `UIModel.format_device_owner_label(owner, mode_name)` formatting clear ownership status strings.
5. `src/openrgb_temp_sync/ui.py`:
   - Replaced Effects tab placeholder with live capability-driven hardware effects surface:
     - Mode selection combobox listing only live supported modes from the selected device.
     - Capability-gated sliders for Speed and Brightness; disabled with clear reason labels when unsupported by the active mode.
     - Direction combobox listing only supported directions (e.g. Left/Right or Up/Down).
     - Mode Color picker enabled only when mode-specific color is advertised.
     - Save to Device button enabled only when mode advertises flash/EEPROM save capability; requires deliberate user confirmation before write.
     - Clear scope notice: hardware effects apply device-wide unless controller advertises zone-native scope.
   - Updated Temperature tab with Target Device Control Ownership status and "Assign to Temperature Sync (Direct Mode)" action.
   - Added App Profile management bar (profile selector, Save Profile dialog, Apply Profile, and Delete Profile).
6. `tests/test_phase03_modes_profiles.py` (New):
   - 14 focused tests verifying:
     - Mode descriptor normalization and flag extraction.
     - Robust handling of partial/missing mode data without crashing.
     - Capability-gated parameter rejection on mode writes.
     - Capability-gated Save to Device rejection and execution.
     - Hardware mode quiescing thermal frames and Direct resume.
     - Missing GPU sensor preventing silent CPU fallback.
     - Missing CPU sensor allowing GPU-only thermal updates.
     - Stale sensor degrading thermal sync while leaving manual/effect devices intact.
     - App profile save, load, delete, atomic persistence, and unmanaged/reset device preservation.
     - Readback mismatch surfacing when hardware fails mode transition.
     - Save-to-device hardware write failure surfacing.
     - Unknown devices and independent RAM zone counts surviving profile reload.
     - UIModel capability summaries and owner labels.
     - Repeated mode switching maintaining owner integrity.

7. `tests/test_duplicate_device_canonical_config.py` (New):
   - Verified canonical stable key persistence for duplicate-name hardware (dual ENE DRAM modules).
   - Independent addressable zone LED counts (JRAINBOW1) and profile settings survive save, load, and apply.
   - Unique legacy display name ("MSI B550") resolves cleanly to canonical stable key.
   - Ambiguous legacy name ("ENE DRAM") is preserved in `unmatched_legacy_profiles` and rejected from silent overwrite.
   - Ambiguous legacy name in `devices` is preserved across `merge_legacy_device_profiles()` long enough for `reconcile_device_profiles_on_save()` to safely relocate it to `unmatched_legacy_profiles` without data loss or duplicate assignment.
   - Verified dual strong-identity DRAM modules ignore legacy name fallback while unique legacy hardware (MSI B550) resolves in regression test `test_legacy_same_name_zone_sizes_ignored_for_duplicate_strong_identity_descriptors`.

## Test Execution Results
- `python -m unittest discover -s tests -v`:
  - Total tests run: 140
  - Passed: 140
  - Failed: 0
  - Exit code: 0
- `git diff --check`: Exit code 0 (clean formatting and line endings).

## Verification Evidence and Criteria
- **Capability-Gated Hardware Effects**: Only modes supported by the device are listed; controls for speed, brightness, direction, and color reflect live flags.
- **Save to Device Gating**: Save operation is disabled for unsaveable modes (e.g. Direct mode) and enabled only for modes with advertised save capability (e.g. static/breathing with manual_save flag); requires explicit user confirmation.
- **Thermal Ownership Isolation**: Transitioning a device to `hardware_mode` or `manual_direct` cancels background thermal writes to that device; resuming thermal sync negotiates Direct mode and immediately dispatches a fresh thermal frame.
- **Independent Device Control**: GPU running hardware effect (Wave/Rainbow), MSI motherboard running thermal sync (JRAINBOW), and RAM running manual color is fully supported simultaneously.
- **Sensor Failure Safety**: Stale sensor degrades the thermal controller state without wiping manual or hardware effect device states; missing GPU does not silently use CPU temperature.
- **Profile Persistence**: Named profiles save atomically to disk with timestamped backup, reload exact device settings, and preserve unmanaged or held devices during apply.
- **Factory Reset Boundary**: Existing `restore_device` remains strictly an in-memory pre-sync snapshot restore; no OEM factory reset is claimed.

## Remaining Risks & Hardware Validation
1. **Live Physical Hardware Verification**: All tests ran against mock SDK structures and simulated failure cases. Physical observation of simultaneous GPU effect, MSI thermal curve, and RAM manual color on the user's live system requires user authorization.
2. **Flash Wear-Out Safety**: Save to Device sends `RGBCONTROLLER_SAVEMODE` which writes to microcontroller EEPROM/flash. The application guards this with explicit user confirmation and never invokes save automatically or on periodic frames.

## Next Phase Handoff
- Phase 03 is code-complete and verified against the unit/integration test suite.
- Follow-up phases 04 (fail-closed manufacturer-default capability) and 05 (packaging/release verification) are recorded separately; exact OEM reset and live hardware behavior remain unverified.
