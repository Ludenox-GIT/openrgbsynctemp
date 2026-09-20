# Phase 3 — Independent JRAINBOW Zone Configuration

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Depends on:** Phase 2 `✅ VERIFIED`  
**Report:** `process/features/unified-rgb-control/reports/phase-3-jrainbow_REPORT_20-09-26.md`

## Objective

Deliver an OpenRGB-style Edit Zone workflow for JRAINBOW1 and JRAINBOW2 independently. Users enter counts; the app validates against controller-reported bounds, resizes through a dispatcher barrier, refreshes the entire parent device, verifies readback, updates LED mapping, and persists only after success.

## Touchpoints

Modify: `device_model.py`, `command_dispatcher.py`, `openrgb_runtime.py`, `config.py`, `desktop_ui.py`, corresponding tests. No vendor reset or flash-save changes.

## Public Contracts

- `ResizeZone` accepts `DeviceId`, `ZoneId`, requested logical count, and expected generation.
- Success requires refreshed parent snapshot and exact count readback. If the protocol lacks reliable readback, result is `APPLIED_UNVERIFIED` and config is not auto-committed until user confirms visible behavior; production UI must not label it verified.
- JRGB/ONBOARD fixed zones show count read-only. Only configurable-size zones enable Edit Zone.
- App-local optional group labels/segments never claim physical topology detection.

## Code Guidance

Pseudocode:

```text
validate integer within reported min/max
enter resize barrier and pause current owner
invoke configure-zone once
refresh full device snapshot
compare requested count with refreshed zone count
on match: persist by stable zone id and restore prior owner
on mismatch/failure: keep old config, show error, refresh authoritative state
```

## Implementation Checklist

- [ ] Add failing tests for the current invisible zone controls, independent port counts, min/max validation, refresh/readback, failed resize rollback, reconnect persistence, and renamed/reordered zones.
- [ ] Add Edit Zone dialog with current count, reported range, numeric input, visual numbered strip, warning text, Apply/Cancel, and no hardware action on Cancel.
- [ ] Show both JRAINBOW1 and JRAINBOW2 even when current count is zero; explain zero as “not configured,” not “port absent.”
- [ ] Submit resize as an exclusive dispatcher barrier; prevent thermal/manual frames during transition.
- [ ] Refresh parent device and rebuild ids/LED tiles after resize; preserve unrelated zone configuration and selection where valid.
- [ ] Persist by stable zone id only after confirmed readback; record requested/current values and OpenRGB result.
- [ ] Apply saved counts on connection through ordered barriers after inventory settles, one port at a time, with failure isolation.
- [ ] Add guided identify/count mode only as reversible Direct-mode preview: light a selected logical LED or short chase, stop immediately on cancel/error, then restore prior owner. It must be user-initiated and must not infer count automatically.
- [ ] Document hub topology: serial chains normally advance addresses; parallel/split hubs may mirror branches, so unique physical selection may be impossible despite a larger logical count.
- [ ] Display a safety note that driver range is not safe load capacity and never suggests rewiring or mixing 5 V JRAINBOW with 12 V JRGB.
- [ ] Live-test JRAINBOW1 and JRAINBOW2 with different counts, close/reopen app, reconnect OpenRGB, reboot, and verify mappings stay independent.

## Manual Hardware Matrix

- Count 0 → configured positive count on each port separately.
- Minimum, typical user-selected, maximum UI-bound validation without driving unknown load, and invalid negative/text/above-max inputs.
- Single selected LED/chase on each port; record whether hub branches mirror.
- JRGB1/JRGB2/ONBOARD remain unchanged.
- Disconnect/reconnect and app restart preserve counts; failed resize leaves last confirmed value.

Do not test the declared software maximum as a physical load test.

## Tests and Evidence

Run targeted model/dispatcher/runtime/config/UI tests, full Python suite, then approved hardware steps. Evidence includes before/after snapshots, command barrier log, readback values, screenshots, port photos/topology description, restart/reconnect result, and user confirmation.

## Rollback

Restore last confirmed per-zone logical counts through the same barrier. If restore fails, stop writes, expose degraded state, and use OpenRGB’s UI as the manual recovery tool; do not guess counts.

## Blast Radius

Motherboard zone indexing and per-LED mapping. Main risk is applying subsequent colors to shifted LEDs; strict readback and full refresh are mandatory.

## Resume and Execution Handoff

One execute agent owns source; one human/operator owns hardware confirmation. Do not run concurrent vendor apps. Green proves zone mapping, not electrical capacity or factory reset.
