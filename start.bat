@echo off
cd /d "%~dp0"
if exist OpenRGBTempSync.exe (
    start "" OpenRGBTempSync.exe
    echo OpenRGB Temp Sync started in background
) else (
    start "" pythonw src/openrgb_tray_app.py
    echo OpenRGB Temp Sync Python started in background
)
ping 127.0.0.1 -n 3 >nul
