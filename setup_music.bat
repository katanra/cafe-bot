@echo off
title Cafe Bot - Music Setup
echo.
echo  =========================================
echo   Cafe Bot  ^|  Music Setup
echo  =========================================
echo.

echo  [1/2] Installing Python packages...
echo        (yt-dlp and PyNaCl)
echo.
py -m pip install yt-dlp PyNaCl
if errorlevel 1 (
    echo.
    echo  Trying python3...
    python3 -m pip install yt-dlp PyNaCl
)
echo.

echo  [2/2] Installing FFmpeg...
echo        (This may take a moment)
echo.
winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
echo.

echo  =========================================
echo   Done! Restart the bot to use music.
echo  =========================================
echo.
pause
