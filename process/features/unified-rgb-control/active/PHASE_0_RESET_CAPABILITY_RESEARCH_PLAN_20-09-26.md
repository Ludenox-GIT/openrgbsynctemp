# Phase 0 — Hardware Capabilities and Genuine Reset Feasibility

**Date:** 20-09-26  
**Status:** ⏳ PLANNED  
**Mode:** Research gate; no production code and no RGB hardware writes  
**Report:** `process/features/unified-rgb-control/reports/phase-0-capability-reset-research_REPORT_20-09-26.md`

## Objective

Lock facts needed by all implementation phases: exact controller inventory, OpenRGB protocol/client compatibility, zone/mode flags, JRAINBOW behavior, and a per-family manufacturer-default-reset verdict. This phase may inspect source, documentation, installed versions, logs, and read-only device enumeration. It must not change modes, colors, zone sizes, profiles, firmware, services, or vendor-app settings.

## Phase Completion Rules

The phase is `✅ VERIFIED` only when integration assumptions, manual inventory review, state evidence, unsupported/error semantics, and user confirmation are recorded. Research completion does not prove reset works; it proves which implementation paths are safe to attempt.

## Touchpoints

Read-only: `src/openrgb_temp_sync/openrgb_runtime.py`, `controller.py`, `ui.py`, `config.py`, `requirements.in`, `requirements.lock`, bundled OpenRGB version/hash/source, OpenRGB SDK/driver source at the pinned commit, MSI Mystic Light public SDK/manual, G.SKILL lighting guide, and Gigabyte GCC/RGB Fusion documentation for the exact GPU controller.

Future report only: the path above. No source/test/config modification.

## Research Checklist

- [ ] Record motherboard, BIOS version, MSI RGB controller identity/firmware where exposed, RAM part numbers/slots/controller paths, GPU exact revision/controller identity, OpenRGB build/hash, and client library/protocol.
- [ ] Capture a sanitized read-only OpenRGB device snapshot: controller fields, duplicate names, locations, types, zones, LED names/counts, `leds_min/max`, mode names/flags, color cardinality, speed/brightness ranges, directions, and save flags.
- [ ] Confirm MSI MAG B550 TOMAHAWK exposes JRGB1, JRGB2, JRAINBOW1, JRAINBOW2, and ONBOARD; document that current reviewed driver declares independent resizable JRAINBOW ranges but cannot infer attached physical count.
- [ ] Compare required metadata with current `openrgb-python==0.3.7` protocol-4 behavior. Decide one of: keep client; adopt a tested upstream client; add a narrow compatibility adapter. Prohibit constant-only protocol bumps.
- [ ] Map controller scope: which modes are controller-wide, which support per-LED Direct colors, which accept mode-specific palettes, and which save automatically/manually/not at all.
- [ ] MSI reset research: inspect official MSI Center behavior on this exact board, public SDK surface, OpenRGB MSI185 implementation, persistence writes, and documented `Default` semantics. Distinguish hardware-effect resume from manufacturer reset.
- [ ] ENE/G.SKILL reset research: establish whether the exact DIMM family has a documented cold-boot default, whether vendor `Reset` resets effect parameters or controller state, and whether changes persist with all software stopped.
- [ ] Gigabyte GPU reset research: identify the exact lighting controller and official GCC/RGB Fusion default action; determine persistence and whether OpenRGB exposes an equivalent verified command.
- [ ] For each family assign `SUPPORTED_VERIFIED`, `SUPPORTED_UNVERIFIED`, `UNSUPPORTED`, or `RESEARCH_REQUIRED`, with source links, device/firmware scope, proposed safe test, recovery plan, and remaining uncertainty.
- [ ] Record electrical/topology guidance: JRGB is 12 V non-addressable; JRAINBOW is 5 V addressable; software maximum is not power capacity; a hub may mirror branches and prevent unique physical addressing.
- [ ] Have the user confirm the inventory and two-port topology description. Unknown fan LED counts remain acceptable because the product supplies guided count entry.

## Factory-Reset Proof Standard

`SUPPORTED_VERIFIED` requires all of the following on the exact family/firmware:

1. A documented vendor action or repeatable, reviewed OpenRGB-equivalent command exists.
2. “Default” is defined by vendor evidence or a reproducible clean baseline, not visual resemblance.
3. The test starts after exporting app/vendor profiles and recording the pre-state.
4. The app disables ownership and auto-start/profile application before reset.
5. After reset, all lighting software is stopped; a cold shutdown and power-on is performed.
6. The default is observed before Windows profile software reapplies anything, then again after Windows starts with the app disabled.
7. No pre-sync snapshot, app profile, generic Rainbow preset, Direct-mode exit, or delete-profile action is part of the proof.
8. Photos/video, timestamps, device/firmware versions, and relevant logs are attached to the report.

If any item is missing, the verdict cannot exceed `SUPPORTED_UNVERIFIED`. If public mechanisms cannot perform the action safely, mark `UNSUPPORTED`; do not synthesize a reset.

## Deliverables and Acceptance

- [ ] Capability matrix covers mainboard, each of two RAM controllers, and GPU.
- [ ] Protocol/dependency decision has a tested compatibility rationale.
- [ ] Reset verdict table names exact evidence and does not generalize from another MSI/G.SKILL/Gigabyte device.
- [ ] Phase 1 can build stable identity without guessing unavailable fields.
- [ ] Phase 5 contains no family implementation task lacking an approved test path.
- [ ] User confirms the inventory matches the PC.

## Public Contracts

The report defines the authoritative capability vocabulary and reset status values used by later phases. No public runtime contract changes in this phase.

## Blast Radius

Read-only. The only risk is misleading research. Mitigate through primary sources, exact versions, explicit inference labels, and `unknown` values.

## Verification Evidence

Source links/commit hashes, sanitized enumeration output, device/firmware table, protocol comparison, reset verdict matrix, and user inventory confirmation.

## Resume and Execution Handoff

Handoff prompt: “Research only. Read this plan, the umbrella, current source, and primary vendor/OpenRGB sources. Do not write source, run vendor controls, resize zones, or change lights. Produce the named report and stop with `DONE_WITH_CONCERNS` if any reset family lacks exact proof.”

Next phase after the report is accepted: `PHASE_1_FOUNDATION_STATE_COMMANDS_PLAN_20-09-26.md`.
