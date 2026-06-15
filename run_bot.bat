@echo off
echo ========================================
echo   Cafe Bot - Installer and Launcher
echo ========================================
echo.

REM Try py launcher first, then full paths
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
    set PIP=py -m pip
    goto run
)

REM Try common Python 3.14 install path
if exist "C:\Users\dabel\AppData\Local\Programs\Python\Python314\python.exe" (
    set PYTHON=C:\Users\dabel\AppData\Local\Programs\Python\Python314\python.exe
    set PIP=C:\Users\dabel\AppData\Local\Programs\Python\Python314\python.exe -m pip
    goto run
)

REM Try Python 3.13
if exist "C:\Users\dabel\AppData\Local\Programs\Python\Python313\python.exe" (
    set PYTHON=C:\Users\dabel\AppData\Local\Programs\Python\Python313\python.exe
    set PIP=C:\Users\dabel\AppData\Local\Programs\Python\Python313\python.exe -m pip
    goto run
)

echo ERROR: Python not found! Please reinstall Python and check "Add to PATH".
pause
exit /b 1

:run
echo Found Python: %PYTHON%
echo.
echo [1/2] Installing requirements...
%PIP% install -r requirements.txt
echo.
echo [2/2] Starting Cafe Bot...
echo.
%PYTHON% bot.py
echo.
echo Bot has stopped. Press any key to close.
pause
