@echo off
cd /d "%~dp0"
title DAV to MP4 Converter

:: Check if pythonw is available to run without console
where pythonw >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" pythonw main.py
    exit /b
)

:: Fallback to python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python main.py
    exit /b
)

echo Python is not detected in PATH.
echo Please run with python installed or run the compiled executable.
pause
