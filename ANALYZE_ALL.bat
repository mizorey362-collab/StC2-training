@echo off
title SC2 Batch Analyzer
echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║         SC2 Replay Batch Analyzer             ║
echo  ║  Processes all replays → Obsidian vault       ║
echo  ╚════════════════════════════════════════════════╝
echo.
echo  Reading replay folder and checking vault...
echo  Already-processed games will be skipped automatically.
echo.

cd /d "%~dp0"
python sc2_batch_analyze.py

if errorlevel 1 (
    echo.
    echo  Something went wrong. Check sc2_batch.log for details.
    pause
)
