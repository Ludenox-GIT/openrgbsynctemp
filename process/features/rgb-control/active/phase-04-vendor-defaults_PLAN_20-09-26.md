# Phase 04 — genuine manufacturer-default restoration

**Date**: 20-09-2026. **Complexity**: Complex phase. **Status**: 🧪 TESTING (Fail-closed capability boundary implemented, manual research required for enablement). **Depends on:** Phase 00 reset matrix and Phase 03 verified. **Report:** `process/features/rgb-control/reports/phase-04_REPORT_20-09-26.md`.

## Overview

Research and implement genuine per-device manufacturer-default restoration only where safe and proven. Read `process/context/all-context.md`; `process/context/tests/all-tests.md` is stale for the RGB test surface.

## Phase Completion Rules

`✅ VERIFIED` is per exact device and requires integration tests, readback, cold-boot/manual comparison, error handling and User Confirmation; unverified paths remain disabled.

## Objective / green check

An enabled `Restore manufacturer defaults` action returns the selected exact device to a verified OEM default, **not** to a pre-sync snapshot, app profile or arbitrary preset. A device without a safe proven method remains explicitly unverified/unsupported. Green is per device; overall requirement is not complete until the target coverage agreed with the user is achieved.

## Research and safety gate before code

For MSI B550 TOMAHAWK, two ENE/G.SKILL RAM modules and Gigabyte RTX 3060 ELITE LHR, gather exact vendor instructions/API or bounded verified controller behavior. Record controller/firmware revisions and whether default means volatile lighting, profile reset, onboard NVRAM or cold-boot pattern. Compare vendor tool behavior in a controlled lab only if it can be safely reproduced on the user's PC; no blind packet replay. Public MSI SDK lacks a generic factory-reset call and depends on Mystic Light installation. G.SKILL documents cold-boot rainbow but its software Reset resets effect settings; do not conflate them. OpenRGB `Reset Zone` clears manual zone configuration, potentially LED count 0, and is not OEM RGB reset. The upstream “Default” mode, if present, must be verified for exact device/firmware and persistence, not inferred from label.

If a vendor method requires MSI Center/RGB Fusion installed permanently, replacing firmware, raw EEPROM writes, clearing CMOS, or ambiguous side effects, stop and return to PLAN/user decision. Do not silently downgrade requirement. A supported stop-owning/handoff control may be offered separately, explicitly not named factory reset.

## Touchpoints and contracts

`openrgb_runtime.py`: per-device reset adapter only for verified paths; `controller.py`: atomic `resetting` transition that drains thermal/off/profile queue, invokes verified path, reads back, releases ownership to unmanaged; `config.py`: do not auto-reapply profile after reset; UI: explicit device name, expected default and confirmation; tests: `test_openrgb_runtime.py`, `test_controller.py`, UI model and config tests. Preserve `restore_pre_sync_snapshot` as separate recovery action or remove with migration only after user agreement. No reset method may be exposed by a generic capability flag without evidence.

## Implementation Checklist and tests

- [ ] Complete per-device proof dossier: official source/tool behavior, exact method, preconditions, persistence level, revert path and risks.
- [ ] For any unproven device, assert reset action disabled with explanation; never return success.
- [ ] Add failing tests for queue draining, mode/thermal/off/profile non-reapply, unsupported rejection, SDK disconnect during reset, partial failure/readback mismatch and confirmation cancel.
- [ ] Implement one device path at a time behind exact model/firmware capability check; no broad `MSI`/`ENE`/`Gigabyte` matching.
- [ ] Run full automated suite and independent source review. On user's hardware, establish non-default state, close other RGB tools, trigger reset, close app, cold boot, observe before Windows and after Windows without app/profile injection; compare documented OEM baseline. Capture exact evidence per device.
- [ ] If any device remains unproven, leave phase/program `🧪 TESTING` or `🚧 BLOCKED` as appropriate; document precise limitation and research next step. Do not mark universal reset delivered.

## Blast radius / rollback / report

Critical hardware state. No raw flash/EEPROM/firmware changes or vendor-tool installation without separate explicit scope decision. Capture current safe profile and recovery instructions before each manual test; manufacturer reset may intentionally destroy custom lighting settings. Report per-device result, firmware/model, logs and cold-boot observations; redact serials. An identical visible color alone does not satisfy proof.

## Public Contracts

Only exact model/firmware paths with a documented `verified` capability may expose reset; `unverified` and `unsupported` reject the action and never return success.

## Acceptance Criteria

Only exact, proven devices expose enabled OEM reset; it drains all pending writes, does not restore a snapshot or reapply a profile, and the independent cold-boot/vendor comparison passes. Each unsupported device is explicitly marked incomplete.

## Verification Evidence

Per-device proof dossier, commands/logs, before/after and cold-boot observations, rejected-path tests and user confirmation are stored in the phase report.

## Agent handoff

Give an exact single-device reset investigation/implementation task to a specialist; independent reviewer checks source and physical test evidence. Next: `phase-05-release-verification_PLAN_20-09-26.md` only after honest reset coverage decision.

## Resume and Execution Handoff

Primary execute anchor: this exact file. Supporting phase files: umbrella plan and Phase 00–03 reports, especially the reset matrix; no generic factory-reset assumption.

**Next Step:** Do not enter implementation until each proposed reset path has its own evidence and scope approval.
