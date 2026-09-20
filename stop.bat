@echo off
setlocal
set "APP_DIR=%~dp0"
echo Stopping OpenRGB Temp Sync...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$targetDir = $env:APP_DIR.TrimEnd('\'); Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $exe = $_.ExecutablePath; if (-not $exe) { return $false }; $isUnder = $exe.ToLower().StartsWith($targetDir.ToLower()); $isApp = ($_.Name -ieq 'OpenRGBTempSync.exe' -and $isUnder); $isPy = ($_.Name -imatch '^pythonw?\.exe$' -and $_.CommandLine -match 'openrgb_tray_app' -and $_.CommandLine -like ('*' + $targetDir + '*')); return ($isApp -or $isPy) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo OpenRGB Temp Sync stopped.
