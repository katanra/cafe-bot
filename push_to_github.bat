@echo off
echo ========================================
echo  Cafe Bot - Push to GitHub
echo ========================================
echo.

cd /d "%~dp0"

REM Remove stuck lock file if present
if exist ".git\config.lock" del /f ".git\config.lock"
if exist ".git\index.lock" del /f ".git\index.lock"

REM Init git if needed
git init
git branch -M main
git remote remove origin 2>nul
git remote add origin https://github.com/katanra/cafe-bot.git

REM Set git identity
git config user.email "dabellstempest@gmail.com"
git config user.name "katanra"

REM Stage all files
git add .
git status

echo.
echo Adding commit...
git commit -m "Initial commit - Cafe Bot with slash commands"

echo.
echo Pushing to GitHub...
echo (A browser window may open asking you to sign in to GitHub - that is normal)
git push -u origin main

echo.
echo ========================================
if %errorlevel%==0 (
    echo  SUCCESS! Code is on GitHub.
) else (
    echo  Something went wrong - see above for details.
)
echo ========================================
pause
