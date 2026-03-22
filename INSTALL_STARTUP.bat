@echo off
title Install SC2 Watcher to Windows Startup
color 0B

echo ============================================================
echo   SC2 Watcher — Windows Startup Installer
echo ============================================================
echo.
echo This will make the watcher launch automatically when you
echo log into Windows (without needing to run it manually).
echo.

:: Target: Windows startup folder for current user
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set WATCHER_DIR=%~dp0
set BAT_PATH=%WATCHER_DIR%START_WATCHER.bat
set SHORTCUT=%STARTUP%\SC2_Watcher.lnk

:: Use PowerShell to create a proper shortcut (not just copy the .bat)
powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT%'); ^
   $s.TargetPath = '%BAT_PATH%'; ^
   $s.WorkingDirectory = '%WATCHER_DIR%'; ^
   $s.WindowStyle = 7; ^
   $s.Description = 'SC2 Replay to Obsidian Watcher'; ^
   $s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo [OK] Shortcut created:
    echo     %SHORTCUT%
    echo.
    echo The watcher will now start automatically on login.
    echo To remove it later, delete that shortcut file.
) else (
    echo.
    echo [FAILED] Could not create shortcut.
    echo You can manually copy START_WATCHER.bat to:
    echo     %STARTUP%
)

echo.
pause
