@echo off
cd /d "%~dp0"
echo Starting OpenRGB Temp Sync in development mode...
if exist dist\OpenRGBTempSync\OpenRGBTempSync.exe (
    start "" "dist\OpenRGBTempSync\OpenRGBTempSync.exe"
) else (
    start "" pythonw src/openrgb_tray_app.py
)