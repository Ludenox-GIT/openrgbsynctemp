@echo off
taskkill /f /im OpenRGBTempSync.exe 2>nul
powershell -Command "gps pythonw -ErrorAction SilentlyContinue | ? { $_.CommandLine -match 'openrgb_temp_sync|openrgb_tray_app' } | Stop-Process -Force"
echo OpenRGB Temp Sync background process stopped!
pause
