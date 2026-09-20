# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

repo_root = os.path.abspath(SPECPATH)
src_dir = os.path.join(repo_root, "src")

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
    [os.path.join(src_dir, 'openrgb_tray_app.py')],
    pathex=[src_dir],
    binaries=[],
    datas=[
        (os.path.join(repo_root, 'third_party', 'THIRD-PARTY-NOTICES.md'), 'licenses')
    ],
    hiddenimports=[
        'openrgb',
        'openrgb.utils',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'psutil',
        'winreg'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OpenRGBTempSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # PyInstaller's default manifest is `asInvoker`, which prevents PawnIO
    # from opening SMBus on Windows. Keep the explicit XML as documentation,
    # but use the supported build switch so the generated PE manifest really
    # requests elevation.
    uac_admin=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest=uac_manifest,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpenRGBTempSync',
)
