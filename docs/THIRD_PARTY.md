# Third-Party Licensing and Source Distribution

OpenRGB Temp Sync redistributes or interfaces with open-source software under various licenses.

## License Inventory

| Component | License | Role in Product |
|---|---|---|
| OpenRGB | GPL-2.0-or-later | Unmodified private child process |
| openrgb-python | GPL-3.0-only | Bundled client library |
| LibreHardwareMonitorLib | MPL-2.0 | Sensor helper library |
| Pillow | HPND | Dynamic tray icon rendering |
| pystray | GPL-3.0-or-later | System tray integration |
| PyInstaller | GPL-2.0 (with exception) | Build tooling |
| Inno Setup | Modified BSD-like | Installer compiler |
| .NET Runtime | MIT | Sensor helper runtime |
| CPython | PSF | Python runtime |

## Source Code Archives
Corresponding source archives for GPL and MPL components are staged under `sources/` and referenced in `third_party/dependencies.lock.json`.
Full legal texts and copyright notices are included in `third_party/THIRD-PARTY-NOTICES.md`.