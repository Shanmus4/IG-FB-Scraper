@echo off
title Instagram Scraper
cd /d "%~dp0"
if exist "..\venv\Scripts\python.exe" (
    "..\venv\Scripts\python.exe" "insta.py"
) else (
    echo Virtual environment not found in parent directory.
    pause
    exit /b
)
pause
