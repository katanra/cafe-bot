@echo off
cd /d "%~dp0"
echo === Git version ===
git --version
echo.
echo === Git remote ===
git remote -v
echo.
echo === Git status ===
git status
echo.
echo === Git log ===
git log --oneline 2>nul || echo No commits yet
echo.
pause
