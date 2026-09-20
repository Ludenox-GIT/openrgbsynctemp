# Phase 5 — Verified Manufacturer-Default Restore

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phase 0 reset verdicts and Phase 4 `✅ VERIFIED`  
**Report:** `process/features/unified-rgb-control/reports/phase-5-vendor-default-reset_REPORT_20-09-26.md`

## Objective

Implement a genuine manufacturer-default restore only for exact device families whose Phase 0 procedure reached `SUPPORTED_VERIFIED`. Unsupported or unresolved families remain clearly disabled. After a successful restore, the app relinquishes ownership and must not reapply a profile or thermal frame.

## Hard Gate

Before source modification, re-research each family against the current firmware/software and Phase 0 report. Delete that family’s implementation checklist from execution if its verdict is not `SUPPORTED_VERIFIED`. The overall product requirement remains incomplete for that family; never substitute session snapshot restore, preset colors, mode exit, profile deletion, or the word `Default` without proof.

## Touchpoints

Potentially add `src/openrgb_temp_sync/reset_runtime.py` containing a small registry and only verified family adapters. Modify dispatcher, state model, config, UI maintenance panel, diagnostics, tests, README/troubleshooting, and packaging only if an official redistributable dependency is approved. Do not depend on MSI Center/GCC/G.SKILL being installed unless the one-app product requirement is explicitly revised.

## Public Contracts

- `ResetCapability` includes status, exact match predicate, evidence/version reference, whether reboot/cold boot is required, user warning, and adapter operation.
- Reset command requires selected exact device ids, typed confirmation, exported recovery bundle, exclusive ownership, and no active vendor controller.
- Success moves controller to `UNMANAGED`, increments generation, clears pending frames, disables startup profile for that device, and records result. Failure also stops normal writes until user chooses recovery/retry.
- UI uses “Restore manufacturer defaults” only for verified adapters; otherwise “Manufacturer restore unavailable” with explanation.

## Implementation Checklist

- [ ] Reconfirm Phase 0 proof and exact firmware match for MSI B550 controller, each ENE RAM controller family, and Gigabyte GPU.
- [ ] Add adapter contract tests: strict match, unsupported default, confirmation, exclusive barrier, no queued writes after reset, typed outcomes, and recovery metadata.
- [ ] Implement the smallest verified adapter per eligible family; reuse OpenRGB operations only when evidence proves equivalence to vendor default.
- [ ] Add maintenance UI with effect description, affected zones, persistence/reboot expectation, recovery export path, typed confirmation, progress, and final `Unmanaged` state.
- [ ] Disable app/profile auto-apply and scheduled thermal ownership for reset targets before executing.
- [ ] Ensure no success is emitted until the adapter’s immediate verification step passes; label any required reboot as `Pending cold-boot verification`, not complete.
- [ ] Keep session snapshot restore as a separately named temporary recovery action; never place it under manufacturer reset.
- [ ] Add tests proving unknown device/firmware, missing dependency, vendor app running, OpenRGB disconnect, partial multi-device reset, timeout, app crash, and reboot-pending states fail honestly.
- [ ] For each eligible family run the cold-boot proof below and attach evidence.
- [ ] For ineligible families verify the button is disabled and no reset command can be constructed through UI, profile import, tray, or internal API.

## Mandatory Cold-Boot Test Per Family

1. Record device id, firmware/controller version, current non-default state, active profiles, and running processes.
2. Export app config, OpenRGB configuration, and vendor profile if available.
3. Disable app auto-start/profile activation for target; close every other RGB owner.
4. Run the verified reset once; capture command/result and immediate state.
5. Exit the app and confirm no app/OpenRGB/vendor lighting process remains and no writes occur.
6. Shut down fully, remove power only if the approved vendor procedure explicitly requires it, then power on.
7. Record lighting before Windows login/profile application.
8. Start Windows with this app and vendor RGB apps disabled; record stable state again.
9. Compare with the documented clean vendor baseline. Have the user confirm.
10. Only then promote the exact family/firmware adapter to `SUPPORTED_VERIFIED` in release metadata.

## Tests and Evidence

Automated adapter/state/dispatcher/UI tests, full Python suite, target-family evidence bundle, no-write-after-reset log, cold-boot video/photos, process list, versions, and user confirmation. Mocks prove orchestration only; they never prove vendor reset.

## Rollback and Recovery

If reset fails, stop app ownership and present the exported recovery path. Recovery may restore an app/OpenRGB profile only at the user’s explicit request and must be labelled recovery, not factory default. Never retry destructive/persistent operations automatically.

## Blast Radius

Potential persistent device state. This is the highest-risk phase. No packet replay, raw SMBus write, flash erase, or vendor-private command is allowed without a separately reviewed procedure, explicit user authorization, and recoverability evidence.

## Verification Evidence

One verdict/evidence section per MSI motherboard, each ENE RAM family, and Gigabyte GPU. A family without cold-boot/profile-independent proof remains unsupported and prevents claiming universal reset support.

## Resume and Execution Handoff

Start with a research specialist, not an executor. Pass the exact family subset approved for implementation. One hardware operator performs tests sequentially. Green proves only listed device/firmware combinations.
