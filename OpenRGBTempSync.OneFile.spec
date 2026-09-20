# -*- mode: python ; coding: utf-8 -*-
"""Temporary single-file release spec.

The vendor executables are bundled as data and extracted by PyInstaller to
``_MEIPASS`` at launch.  This keeps the shipped release to one EXE while
preserving the OpenRGB and SensorBridge child-process layout.
"""
import os

repo_root = os.path.abspath(SPECPATH)
src_dir = os.path.join(repo_root, "src")
vendor_dir = os.path.join(repo_root, "vendor")

uac_manifest = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
"""

a = Analysis(
    [os.path.join(src_dir, "openrgb_tray_app.py")],
    pathex=[src_dir],
    binaries=[],
    datas=[
        (os.path.join(repo_root, "third_party", "THIRD-PARTY-NOTICES.md"), "licenses"),
        (os.path.join(vendor_dir, "OpenRGB"), "vendor/OpenRGB"),
        (os.path.join(vendor_dir, "sensor-bridge"), "vendor/sensor-bridge"),
    ],
    hiddenimports=[
        "openrgb",
        "openrgb.utils",
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "psutil",
        "winreg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="OpenRGBTempSync-Final",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    uac_admin=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest=uac_manifest,
)
