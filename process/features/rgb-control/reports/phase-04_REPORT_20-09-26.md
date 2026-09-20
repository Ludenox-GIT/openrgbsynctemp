# Phase 04 Report - genuine manufacturer-default restoration

**Date**: 2026-09-20
**Status**: 🔨 CODE DONE / 🧪 UNVERIFIED (fail-closed reset capability; no exact MSI/ENE/Gigabyte manufacturer-reset path has been proven)
**Component**: openrgb_runtime.py, controller.py, ui.py

## Summary
Added structured unsupported/unverified manufacturer default reset capability and exposed it to the UI.
- OpenRGBSupervisor.get_reset_capability and restore_manufacturer_defaults added.
- The devices MSI MAG B550 TOMAHAWK, ENE DRAM, and Gigabyte RTX 3060 are classified as unverified and fail closed.
- Any other device is unsupported and fails closed.
- The UI exposes a disabled Restore Manufacturer Defaults button with a tooltip for these devices.
- The Restore Pre-Sync Snapshot button remains independent and functionally intact.
- TDD unit tests (test_phase04_vendor_defaults.py) implemented and passing.
- UI components `factory_reset_btn` and `factory_reset_label` have been added to `SettingsGUI` and wired properly into the selection and action lifecycle via `_update_factory_reset_state()`.
- Headless UI tests (`test_factory_reset_button_state`, `test_factory_reset_snapshot_buttons_exist`) successfully cover disabled and verified states.
- Manual cold-boot validation is still required for any verified paths if they are ever enabled in the future.

## Next steps
- Continue research on genuine OpenRGB or vendor-tool commands for MSI, Gigabyte, and ENE hardware.
- If verified commands are established, update the capability classification in OpenRGBSupervisor.
