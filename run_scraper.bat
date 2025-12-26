@echo off
title Social Media Scraper
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    ".\venv\Scripts\python.exe" "main.py"
) else (
    echo Virtual environment not found. Please run "python -m venv venv" first.
    pause
    exit /b
)
pause
