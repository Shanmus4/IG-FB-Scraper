@echo off
title Facebook Scraper
cd /d "%~dp0"
if exist "..\venv\Scripts\python.exe" (
    "..\venv\Scripts\python.exe" "facebook.py"
) else (
    echo Virtual environment not found in parent directory.
    pause
    exit /b
)
pause
