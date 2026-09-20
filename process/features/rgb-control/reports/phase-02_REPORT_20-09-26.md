# Phase 02 Report — Device UI, Manual Color and Edit Zone

**Date**: 20-09-2026
**Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (automated UI/zone contracts and reversible JRAINBOW smoke pass; full visual/topology confirmation remains pending)
**Depends on**: Phase 01 Verified

## Executive Summary
Phase 02 implements an OpenRGB-like device -> zone -> LED selection UI, manual color controls (RGB/HSV/Hex and swatches), transactional Edit Zone dialog for resizable zones (specifically JRAINBOW1 and JRAINBOW2), distinct labeling of duplicate ENE DRAM modules (RAM A and RAM B), and full preservation of thermal sync and tray controls.

All hardware writes strictly route through supervisor APIs (`supervisor.set_colors`, `supervisor.resize_zone`); no direct SDK object writes are performed from UI components.

## Touchpoints and Changed Files
1. `src/openrgb_temp_sync/ui_model.py` (New):
   - `UIModel.build_device_tree_items`: Formats distinguishable labels for duplicate devices (e.g. `ENE DRAM (RAM A)` and `ENE DRAM (RAM B)`), preserves stable descriptor keys, and surfaces ambiguity.
   - `hex_to_rgb`, `rgb_to_hex`, `rgb_to_hsv`, `hsv_to_rgb`: Native standard-library (`colorsys`, `re`) color validation and conversions.
   - `ColorState`: Synchronized representation of active RGB, HSV, and Hex values with strict range clamping.
   - `build_target_colors`: Scope-isolated color payload builder ensuring that applying color to a specific device, zone, or single/multi LED selection never modifies unselected targets.
   - `UIModel.is_zone_resizable`: Validates whether a zone supports independent count resizing.
   - `EditZoneTransaction`: Transactional wrapper for zone count adjustments: validates integer bounds -> pauses target controller writes (`manual_direct`) -> invokes `supervisor.resize_zone` -> refreshes inventory -> validates exact readback equality -> persists to `config.json` only upon exact match. Canceling discards staged edits without writing.
2. `src/openrgb_temp_sync/ui.py` (Updated):
   - Refactored settings window to a 3-column OpenRGB-like layout:
     - Left: Devices & Zones Treeview with distinct RAM A/RAM B entries and MSI motherboard zone hierarchy.
     - Center: Target Selection header, capability-gated Edit Zone action (enabled only for resizable zones, disabled for 12V 4-pin JRGB1/2), Select All / Deselect All, and scrollable numeric LED list.
     - Right: 3-tab Notebook (`Manual | Effects | Temperature`):
       - `Manual`: Scope preview label, color swatch canvas, `#RRGGBB` hex entry, numeric RGB spinboxes (0-255), numeric HSV spinboxes (0-359, 0-100%, 0-100%), preset swatches, and "Apply Color to Scope" routing through `supervisor.set_colors`.
       - `Effects`: Honest pending notice documenting that hardware effects are scheduled for Phase 04.
       - `Temperature`: Fully preserved temperature thresholds (Low/Mid/High temps and color choosers), transition speed slider, screensaver integration checkbox, and pre-sync snapshot restore/resume button.
   - Header with connection badge and Rescan button.
   - Preserved thread-safe `show()` and `hide()` methods, `save()` validation and error reporting, diagnostics export, and tray integration.
3. `tests/test_ui_model.py` (New):
   - 10 unit tests verifying duplicate labels/keys, empty descriptor handling, color conversions & clamping, scope targeting isolation, capability-disabled controls, and EditZoneTransaction range/cancel/apply/readback/rejection.
4. `tests/test_ui.py` (New):
   - 6 integration tests verifying GUI creation, tab structure, distinct duplicate device rendering, empty device handling, targeted manual color writes, and resizable vs fixed Edit Zone button states.
5. `process/features/rgb-control/reports/phase-02_REPORT_20-09-26.md` (New):
   - Verification record and execution status.

## Test Execution Results
- `python -m unittest discover -s tests -v`:
  - Total tests run: 91
  - Passed: 91
  - Failed: 0
  - Exit code: 0
- `git diff --check`: Exit code 0 (clean formatting and line endings).

## Verification Evidence and Criteria
- **Device Tree Disambiguation**: Identical ENE DRAM devices are assigned distinct `RAM A` / `RAM B` labels and indexed by stable descriptor keys; ambiguity is visible.
- **Empty Inventory Safety**: UI cleanly displays empty state without throwing exceptions when no devices, zones, or LEDs are present.
- **Scope Isolation**: Setting color on a single LED or zone modifies only target indices; other LEDs on the device retain their existing colors.
- **Transactional Edit Zone**: JRAINBOW1 and JRAINBOW2 are independently editable within descriptor min/max bounds; changes are verified by inventory readback before config persistence; Cancel makes no writes; JRGB1/2 non-resizable controls remain disabled.
- **Manual Color Validation**: Hex, RGB, and HSV inputs are bidirectional, validated, and clamped; color swatch updates live.
- **Thermal Sync Compatibility**: All Phase 01 tests and thermal loop behaviors remain green.

## Remaining Risks & Honest Hardware Validation
1. **Live Physical Hardware Verification**: Automated tests verify all models, transactions, readbacks, and UI components against mock SDK structures. Real visual confirmation (e.g. RAM A red / RAM B blue, JRAINBOW1 vs JRAINBOW2 independent physical LED illumination, and JRGB non-addressable single-channel behavior) requires running on the user's physical machine with user approval.
2. **ARGB Hub Wiring**: On systems using parallel ARGB fan hubs on JRAINBOW headers, physical LED count corresponds to the longest daisy-chained fan or hub slice; software count controls data packet length.

## Next Phase Handoff
- Phase 02 is code-complete and verified against the unit/integration suite.
- Next scheduled plan: `phase-03-modes-thermal-profiles_PLAN_20-09-26.md`.
