@echo off
title SC2 Replay Watcher
color 0A

echo ============================================================
echo   SC2 ^-^> Obsidian Watcher
echo   Watching for new replays...
echo   Close this window to stop.
echo ============================================================
echo.

:: Change to the folder where this .bat file lives
cd /d "%~dp0"

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3 from python.org
    pause
    exit /b 1
)

:: Run the watcher
python sc2_watcher.py

echo.
echo Watcher stopped.
pause
