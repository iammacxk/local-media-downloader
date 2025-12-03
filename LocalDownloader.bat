@echo off
title Ultimate Downloader Pro - Server
color 0A
cd /d "%~dp0"

echo ========================================================
echo    ! Ultimate Downloader Pro Launcher
echo ========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] Python not found! Please install Python first.
    pause
    exit
)

:: 2. Update libraries (To ensure yt-dlp is latest)
echo [INFO] Checking for updates...
pip install --upgrade yt-dlp flask >nul 2>&1

:: 3. Open Web App
echo [INFO] Opening Web App...
timeout /t 2 >nul
start "" "http://127.0.0.1:5000"

:: 4. Start Server
echo [INFO] Starting Server...
echo.
echo --------------------------------------------------------
echo  ! Program is ready! (Do not close this window)
echo  ! To stop the program, close this window.
echo --------------------------------------------------------
echo.

python app.py

:: If program crashes
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERROR] The program terminated unexpectedly.
    pause
)