# Phase 00 report — capability and reset feasibility

**Status:** 🧪 TESTING / read-only audit complete; user confirmation and exact-hardware reset proof remain pending.  
**Date:** 20-09-2026  
**Plan:** process/features/rgb-control/active/phase-00-capabilities-reset_PLAN_20-09-26.md

## Scope and safety

This phase performed repository inspection, installed-version checks, pinned OpenRGB source research, WMI metadata inspection and read-only SDK enumeration. It did not edit application source/configuration, call RGB mutators, resize a zone, save a mode, flash firmware, write EEPROM/HID/SMBus, stop an RGB process, or change physical LED state. The only phase artifact written is this report. Pre-existing dirty worktree changes were preserved.

The application helper was not used for enumeration because its connect path calls configure_devices_direct_mode immediately. Instead, a temporary Python process instantiated openrgb.OpenRGBClient against the already-running loopback server, printed metadata and called stop_connection in finally. It did not call set_mode, set_colors, set_color, resize, save_mode, off, or any other RGB-controller mutator.

## Commands and results

Read-only commands executed included:

- git status --short; git diff --stat; git log -1 --format='%H%n%ad%n%s' --date=iso-strict
- python --version
- python -m unittest discover -s tests -v
- Get-CimInstance Win32_OperatingSystem, Win32_BaseBoard, Win32_BIOS, Win32_PhysicalMemory and Win32_VideoController
- Get-NetTCPConnection -LocalPort 6742; Get-CimInstance Win32_Service for OpenRGB
- Get-FileHash on the bundled OpenRGB archive/executable and dependency files
- PowerShell Invoke-WebRequest to read pinned OpenRGB raw source in memory only

Final automated test result at the audit checkpoint: 135 tests ran, 135 passed, 0 failed, exit code 0, duration 2.602 seconds. The current integrated suite is 140/140 after the MSI custom-mode regression. This is a mock/unit result and does not prove hardware control or factory reset. Release/build verification was not run because it creates artifacts and belongs to Phase 05.

Repository HEAD was 68afaf0ed0ac5af9f3ab37c7ddf1e3def21baebe. The worktree was already dirty with the application refactor, tests, installer/build files and process plans. No unrelated change was reverted.

Runtime baseline: Python 3.12.10, openrgb-python 0.3.7, pywin32 312, psutil 7.2.2. The installed SDK declares OPENRGB_PROTOCOL_VERSION = 4 and the server accepted protocol 4 with maximum 4. The bundled OpenRGB manifest pins release 1.0 artifact suffix 81bbe18, source commit 81bbe18a84c2e507006f19dd252e397e40a56bfe. The staged archive SHA-256 is 182A52A3C97C4C4AE52C80286B4260C9666C51C3447DBC416EE8945F66192E90, matching the manifest.

Windows is Windows 10 Pro 64-bit build 19045. The board is Micro-Star International MAG B550 TOMAHAWK (MS-7C91), version 2.0. BIOS is A.L2, WMI release date 2026-08-14. Both an automatic OpenRGB service and an interactive OpenRGB GUI were running; this was recorded but not changed.

## Live read-only device inventory

The SDK returned four controllers. Session IDs are not persistent identity keys.

| Session | Device and metadata | Zones/count | Reset |
|---:|---|---|---|
| 0 | ENE DRAM; vendor ENE; version AUDA0-E6K5-0101; no serial; I2C PawnIO SMBus PIIX4 0, address 0x72 | DRAM linear, 8 LEDs, fixed 8–8 | Unverified |
| 1 | ENE DRAM; vendor ENE; version AUDA0-E6K5-0101; no serial; same bus, address 0x73 | DRAM linear, 8 LEDs, fixed 8–8 | Unverified |
| 2 | Gigabyte AORUS GeForce RTX 3060 ELITE LHR; RGB Fusion 2 GPU Device; no version/serial; Nvidia NvAPI I2C GPU 0, address 0x70 | Five fixed single zones, one LED each | Unverified |
| 3 | MSI MAG B550 TOMAHAWK (MS-7C91); Mystic Light Device (185-byte); firmware AP/LD 10.4 / 1.5; serial A020200409A4; HID PID 0x7C91 | JRGB1 1, JRGB2 1, JRAINBOW1 2, JRAINBOW2 2, ONBOARD 6 | Unverified |

WMI reports two 8 GiB modules with part F4-3600C18-8GTZN, 3600 MT/s, bank labels P0 CHANNEL A/B, but manufacturer Unknown and both DeviceLocator values DIMM1. The likely Trident Z RGB/Neo family is an inference from the part number, not a verified manufacturer field. OpenRGB SMBus addresses 0x72 and 0x73 are the usable current differentiator.

### Live modes

Both ENE modules expose Direct, Off, Static, Breathing, Flashing, Spectrum Cycle, Rainbow, Chase Fade, Chase and Random Flicker. Direct/Static/Breathing/Flashing/Chase modes expose per-LED colors; other modes expose the flags reported by the controller, including speed and direction where applicable. Their live mode flags do not contain the manual-save bit, even though the pinned ENE driver advertises save support conditionally through its enable_save setting.

The Gigabyte GPU exposes Direct, Pulse, Flash, Double Flash, Color Cycle, Gradient, Wave, Color Shift and Tricolor. It has five fixed single zones. Color Shift supports 1–8 mode-specific colors; Tricolor supports 1–3. The live flags show save capability on applicable modes.

The MSI mainboard exposes Direct, Static, Breathing, Flashing, Double flashing, Lightning, Meteor, Color ring, Planetary, Double meteor, Energy, Blink, Clock, Color pulse, Color shift, Color wave, Marquee, Rainbow wave, Visor, Rainbow flashing, Color ring double flashing, Stack and Fire. The later UI must generate controls from mode flags and scope; it must not assume every effect supports the same colors/speed/brightness.

## Capability and JRAINBOW contract

The pinned OpenRGB MSI source maps PID 0x7C91 to JRGB1, JRGB2, JRAINBOW1, JRAINBOW2 and ONBOARD with per-LED direct support. JRGB1/JRGB2 are one logical channel each; JRAINBOW1/2 are addressable. The driver software limits are JRAINBOW1 200 and JRAINBOW2 240. They are not electrical power ratings.

The live server currently reports JRAINBOW1 count 2, range 0–200, and JRAINBOW2 count 2, range 0–240. A count is software-addressable configuration, not automatic physical LED detection. It cannot prove how many LEDs exist on a three-fan chain, case fan or hub and must not be used as an electrical-safety limit.

OpenRGB’s pinned Zone Editor binds the slider/spinbox to live zone minimum/current/maximum and only enables them for manually configurable zone flags. The application’s future Edit Zone transaction must pause writes to the controller, validate the selected zone and range, resize only the selected JRAINBOW, request/read back exact count, persist only after successful readback and refresh the LED grid. Cancel must not write or persist. If a hub mirrors one data signal, several physical fans may still show the same address; the app must explain this rather than inventing topology.

The installed SDK’s Zone.resize already refreshes parent data after sending the resize packet. The correct gap for later work is explicit requested-versus-readback verification and serialized writes, not a speculative second refresh.

## Reset feasibility

### MSI mainboard — UNVERIFIED

The public MSI Mystic Light SDK 1.0.0.08 documents device/LED enumeration, colors, styles, brightness, speed and MLAPI_Release, but no universal FactoryReset or immutable factory-profile API. It requires an MSI Mystic Light-related application to be installed. The OpenRGB 185-byte driver reads/writes the active controller configuration and can save it; that is not proof of a factory template or factory erase. OpenRGB’s Reset Zone/manual-configuration reset is not a manufacturer reset.

Proof needed: exact board/firmware behavior in MSI Center/Mystic Light, with other RGB controllers closed; compare deliberate non-default state to vendor-defined state after reset, reconnect and full cold boot. No raw 185-byte replay, EEPROM write, BIOS/CMOS reset or firmware action is allowed under this phase.

### ENE/G.SKILL RAM A/B — UNVERIFIED

OpenRGB exposes ENE SMBus controls but no generic factory-reset packet. G.SKILL’s official guide documents a software Reset for lighting-effect settings; its official troubleshooting guide separately documents rainbow lighting on cold boot before Windows. Those observations are not equivalent to an EEPROM erase. Each module must be proven independently using 0x72 and 0x73; the legacy name ENE DRAM cannot be used for reset targeting.

### Gigabyte GPU — UNVERIFIED

The pinned Gigabyte controller supports direct/effects/save. The official AORUS product page documents RGB Fusion 2.0 and has separate PCB revision paths, but no exact model/revision factory-reset API or cold-boot proof was found. Static/Rainbow presets must not be called manufacturer reset. No firmware or arbitrary I2C experiment is in scope.

References:

- OpenRGB SDK: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Documentation/OpenRGBSDK.md
- MSI RGB controller: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Controllers/MSIMotherboardController/MSIMotherboard185Controller/RGBController_MSIMotherboard185.cpp
- MSI 185-byte controller: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Controllers/MSIMotherboardController/MSIMotherboard185Controller/MSIMotherboard185Controller.cpp
- OpenRGB Zone Editor: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/qt/OpenRGBZoneEditorDialog/OpenRGBZoneEditorDialog.cpp
- ENE controller: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Controllers/ENESMBusController/RGBController_ENESMBus.cpp
- Gigabyte controller: https://github.com/CalcProgrammer1/OpenRGB/blob/81bbe18a84c2e507006f19dd252e397e40a56bfe/Controllers/GigabyteRGBFusion2GPUController/RGBController_GigabyteRGBFusion2GPU.cpp
- MSI SDK: https://storage-asset.msi.com/files/pdf/Mystic_Light_Software_Development_Kit.pdf
- G.SKILL reset/cold boot guide: https://www.gskill.com/community/1584933243/1704357891/Trident-Z-Lighting-Control-Software-Guides
- Gigabyte product/support page: https://www.gigabyte.com/Graphics-Card/GV-N3060AORUS-E-12GD-rev-10/support

## Final audit checklist

| Check | Result | Evidence / limit |
|---|---|---|
| Worktree preservation | PASS | Existing dirty state preserved; only this report added |
| Read-only SDK enumeration | PASS | Protocol 4 metadata request; no RGB mutator invoked |
| OpenRGB dependency baseline | PASS | openrgb-python 0.3.7; pinned artifact/hash checked |
| Protocol compatibility claim | PASS | Client max/default protocol 4; protocol 5/6 are not assumed |
| Two-RAM identity | PASS for canonical integration; ambiguous legacy names stay unmatched | 0x72/0x73 produce distinct stable descriptors; legacy `ENE DRAM` is rejected rather than guessed |
| JRAINBOW capability evidence | PASS | Separate ranges/counts for both headers recorded |
| JRAINBOW user UI | PASS in automated/live smoke scope | Separate zone selectors, Edit Zone bounds, exact readback and persistence-after-success are implemented; physical topology remains unproven |
| Physical LED auto-detection | NOT PROVEN | SDK count is configuration, not physical topology |
| Genuine MSI reset | FAIL / unverified | No public universal reset API or factory template found |
| Genuine RAM reset | FAIL / unverified | Software Reset and cold-boot rainbow are separate evidence |
| Genuine GPU reset | FAIL / unverified | Exact PCB/revision reset behavior not proven |
| Automated test suite | PASS | 140/140 current integrated suite; audit checkpoint was 135/135 |
| Hardware smoke/reset | NOT RUN | Correctly excluded from read-only Phase 00 |
| Build/release verification | NOT RUN | Reserved for Phase 05 to avoid artifact mutation |

## Handoff blockers

1. Canonical identity, ambiguous-name rejection and non-mutating SDK connect are implemented; continue to preserve these contracts during future changes.
2. Phase 02/03 implement separate JRAINBOW1/JRAINBOW2 Edit Zone transactions with bounds, readback and persistence-after-success; a physical fan/hub topology is still not auto-detectable.
3. Phase 04 must keep manufacturer reset disabled for every target until per-model/per-firmware, profile-independent cold-boot proof exists. Existing snapshot restore remains a separate operation.
4. Phase 05 must keep live mode readback failures visible and complete the missing .NET 8/Inno Setup release toolchain before a signed installer claim.

This report is ready for parent-agent review. It is not a VERIFIED phase: automated tests pass, but exact-hardware reset and user-confirmed hardware behavior remain outstanding. No Phase 01 implementation should be interpreted as evidence that genuine reset has been solved.
