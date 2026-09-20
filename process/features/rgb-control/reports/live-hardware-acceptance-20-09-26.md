# Live hardware acceptance — 20-09-2026

## Result

**PASS with one hardware capability limitation.** The final onedir build is installed and running from `C:\Program Files\OpenRGB Temp Sync`. OpenRGB is launched by the `OpenRGBTempSync` Scheduled Task with `HighestAvailable`; the SDK sees all four controllers, including both ENE DRAM modules.

## Root causes found and fixed

1. The missing RAM was caused by a non-elevated OpenRGB process. The OpenRGB log showed missing/failed PawnIO SMBus modules, so ENE DRAM detection was skipped. The app now refuses to launch the bundled engine without elevation, and the installed Scheduled Task is configured with `HighestAvailable`.
2. MSI manual color writes were sent while the board was still in a hardware effect (for example `Rainbow wave`). The SDK accepted the packet but read back the effect's generated colors. Manual color control now negotiates `Direct` first and then verifies the per-LED readback.
3. Zone resize/restore must happen in `Direct`; restore now enters `Direct` before resizing JRAINBOW zones, prefers an explicitly requested `vendor_default` baseline, and verifies the restored mode after the hardware readback settles.

## Final inventory

| Controller | Zones/readback | Advertised modes |
|---|---:|---:|
| ENE DRAM (RAM A) | DRAM: 8 | 10 |
| ENE DRAM (RAM B) | DRAM: 8 | 10 |
| Gigabyte AORUS GeForce RTX 3060 ELITE LHR | GPU zones 1–5: 1 each | 9 |
| MSI MAG B550 TOMAHAWK (MS-7C91) | JRGB1: 1, JRGB2: 1, JRAINBOW1: 2, JRAINBOW2: 2, ONBOARD: 6 | 23 |

## Live matrix

- Device discovery: **4/4**.
- Mode writes/readback: **52 attempted; 51 pass; 0 unexpected failures**.
- Known hardware limitation: Gigabyte RTX 3060 `Pulse` is advertised but the firmware immediately reads back `Direct`; it is reported as unsupported, never presented as a false success.
- Per-LED color writes: **4/4 pass** (including RAM A, RAM B, GPU and MSI).
- Vendor baseline restore: **4/4 pass**; final modes were RAM `Rainbow`, GPU `Direct`, MSI `Rainbow wave`; zone counts were restored exactly.
- JRAINBOW edit test: JRAINBOW1 `2 → 3`, JRAINBOW2 `2 → 4`, read back successfully, then restored to `2/2`.
- Screenshot reproduction: MSI `Rainbow wave → Direct → white per-LED`; readback returned `(255,255,255)` and restore returned to `Rainbow wave`.

The machine-side matrix output is captured in `live-hardware-matrix-20-09-26.json`; the summary was `device_count=4`, `mode_total=52`, `mode_pass=51`, `mode_unsupported=1`, `mode_fail=0`, `color_pass=4`, `restore_pass=4`.

## Automated/package gates

- Python regression suite: **164/164 passed**.
- `scripts/verify-release.ps1`: developer contracts passed.
- PyInstaller onedir build: passed with OpenRGB and SensorBridge payloads staged.
- Final app SHA-256: `FFCC75BE0511E41131A30701A0755AAF189B8ADA1A19008C6E220DA1F4B24878`.
- Portable archive SHA-256: `D30C669FEDAC98DD576EA7E98FC560F38B7D10C6953D29445D5B331359692A3F`.
- Required payloads verified in the installed directory: `vendor\OpenRGB\OpenRGB.exe`, `LpcIO.bin`, `SmbusPIIX4.bin`, and `vendor\sensor-bridge\OpenRGBTempSync.SensorBridge.exe`.
- Final OpenRGB log: `%LOCALAPPDATA%\OpenRGBTempSync\openrgb_config\logs\OpenRGB_20260920_154745.log`; it records successful PawnIO initialization and both ENE DRAM controllers.

## Delivery note

The full portable onedir build is installed and running. An Inno Setup installer was not generated because `ISCC.exe` is not installed on this PC; this does not affect the installed full build or the portable ZIP. A genuine OEM factory-reset protocol remains deliberately unclaimed; the implemented reset uses the user-confirmed `vendor_default` hardware snapshot and verifies its readback.
