# Troubleshooting Guide

## 1. Engine & Port 6742 Conflicts

- **Rogue / Wildcard Listeners**:
  If port 6742 is listening on `0.0.0.0` or a foreign LAN IP, OpenRGB Temp Sync will block connection with an `UNSAFE_WILDCARD` conflict to prevent exposing an unauthenticated RGB socket to your local network.
  *Remediation*: Close the external application binding to 6742 or reconfigure it to bind strictly to `127.0.0.1`.

- **External OpenRGB**:
  If a compatible OpenRGB server is already running on `127.0.0.1:6742`, the app safely adopts the connection and labels status as `External OpenRGB`. The app will not terminate external instances on exit.

## 2. Sensor Degraded States

- **CPU / GPU Temperature Shows None**:
  The sensor bridge uses `LibreHardwareMonitorLib`. Ensure the application runs with Administrator privileges (`requireAdministrator`) so hardware sensors (especially AMD CPU and motherboard sensors) can be queried.
- **Sensor Stream Stale (>10s)**:
  If hardware polling hangs, the app will transition to `DEGRADED_SENSOR` and freeze RGB updates to prevent sending invalid color signals. Use "Retry Engine" in settings or tray.

## 3. PawnIO / Driver Initialization

- OpenRGB requires the PawnIO driver for direct memory/SMBus hardware access (e.g. ENE DRAM RGB on G.Skill RAM or motherboard lighting). If PawnIO is missing or requires a system restart, RGB devices may report 0 controllable zones.
- After installing PawnIO via the installer, reboot the system if prompted.

## 4. Diagnostic Export

Open the settings window from the system tray and click **Export Diagnostics**. This generates a redacted JSON payload summarizing runtime state, port status, detected device counts, and recent sensor logs without exposing private data.