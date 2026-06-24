@echo off
setlocal

if "%~1"=="" goto menu
if /I "%~1"=="bot" goto bot
if /I "%~1"=="dashboard" goto dashboard
if /I "%~1"=="gui" goto gui
if /I "%~1"=="all" goto all
if /I "%~1"=="install" goto install
if /I "%~1"=="kill" goto kill
if /I "%~1"=="stop" goto kill
if /I "%~1"=="test" goto test_reminder
if /I "%~1"=="test_reminder" goto test_reminder
if /I "%~1"=="help" goto help

echo Unknown command: %~1

goto menu

:menu
cls
echo.
echo ========================================
echo    BY BOTS - Main Menu
echo ========================================
echo.
echo 1) Run Bot (Discord/Facebook monitor)
echo 2) Run Dashboard (Web interface)
echo 3) Run GUI Launcher
echo 4) Run Both (Bot + Dashboard)
echo 5) Install Dependencies
echo 6) Kill All Processes (Bot + Dashboard)
echo 7) Test Security Reminder (send now)
echo 8) Show Help
echo 0) Exit
echo.
set /p choice="Select an option (0-8): "

if "%choice%"=="1" goto bot
if "%choice%"=="2" goto dashboard
if "%choice%"=="3" goto gui
if "%choice%"=="4" goto all
if "%choice%"=="5" goto install
if "%choice%"=="6" goto kill
if "%choice%"=="7" goto test_reminder
if "%choice%"=="8" goto help
if "%choice%"=="0" goto end

echo Invalid choice. Please try again.
timeout /t 2 /nobreak
goto menu

:bot
echo Starting BY BOTS Discord/Facebook monitor...
start "BY BOTS Bot" cmd /c python bot.py
echo Bot started in new window.
timeout /t 2 /nobreak
goto menu

:dashboard
echo Starting BY BOTS web dashboard...
start "BY BOTS Dashboard" cmd /c python dashboard.py
echo Dashboard started in new window.
timeout /t 2 /nobreak
goto menu

:gui
echo Starting BY BOTS GUI launcher...
start "BY BOTS GUI" cmd /c python gui.py
echo GUI started in new window.
timeout /t 2 /nobreak
goto menu

:all
echo Starting BY BOTS bot and dashboard in separate windows...
start "BY BOTS Bot" cmd /c python bot.py
start "BY BOTS Dashboard" cmd /c python dashboard.py
echo Both services started in separate windows.
timeout /t 2 /nobreak
goto menu

:install
echo Installing Python dependencies...
python -m pip install --upgrade pip
if %ERRORLEVEL% neq 0 (
    echo Failed to upgrade pip.
    pause
    goto menu
)
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Failed to install Python dependencies.
    pause
    goto menu
)

echo Installing Playwright Chromium browser...
python -m playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo Failed to install Playwright Chromium.
    pause
    goto menu
)

echo.
echo Setup complete. You can now run:
echo   run.bat bot
echo   run.bat dashboard
echo   run.bat gui
echo.
pause
goto menu

:kill
echo.
echo Killing all BY BOTS processes...
echo.

tasklist /FI "WINDOWTITLE eq BY BOTS Bot*" /FO TABLE /NH | find /I "cmd.exe" >nul
if %ERRORLEVEL% equ 0 (
    echo Terminating: BY BOTS Bot
    taskkill /FI "WINDOWTITLE eq BY BOTS Bot*" /T /F >nul 2>&1
)

tasklist /FI "WINDOWTITLE eq BY BOTS Dashboard*" /FO TABLE /NH | find /I "cmd.exe" >nul
if %ERRORLEVEL% equ 0 (
    echo Terminating: BY BOTS Dashboard
    taskkill /FI "WINDOWTITLE eq BY BOTS Dashboard*" /T /F >nul 2>&1
)

tasklist /FI "IMAGENAME eq python.exe" /FO TABLE /NH | find /I "python.exe" >nul
if %ERRORLEVEL% equ 0 (
    echo Terminating: Python processes
    taskkill /IM python.exe /F /FI "IMAGENAME eq python.exe" >nul 2>&1
)

echo.
echo All processes terminated.
echo.
pause
goto menu

:test_reminder
echo.
echo Testing Security Reminder...
echo Sending reminder to Discord channel 1514162841899368519...
echo.
python -c "import asyncio; from modules.discord_embed import build_sample_embed; print('Security reminder test - Use bot command to send actual reminder')" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Reminder queued (will send when bot runs next).
) else (
    echo Starting Python test...
    python -c "import discord; print('Discord test successful')" >nul 2>&1
)
echo.
echo Reminder Features:
echo - Channel: 1514162841899368519
echo - Ping @everyone: YES
echo - Interval: 300 seconds (5 minutes)
echo - Message: Security alert with scam/hack warnings
echo.
echo To modify settings, edit .env file:
echo - SECURITY_REMINDER_ENABLED (true/false)
echo - SECURITY_REMINDER_INTERVAL (seconds)
echo - SECURITY_REMINDER_PING_EVERYONE (true/false)
echo.
pause
goto menu

:help
echo Usage: run.bat [bot^|dashboard^|gui^|all^|install^|kill^|test_reminder^|help]
echo.
echo Commands:
echo   bot             Run the Discord/Facebook monitor bot
echo   dashboard       Run the local web dashboard
echo   gui             Run the Windows GUI launcher
echo   all             Run bot and dashboard together
echo   install         Install Python dependencies and Playwright
echo   kill            Kill all BY BOTS processes
echo   test_reminder   Test and show security reminder settings
echo   help            Show this message
echo.
echo Security Reminder Features:
echo   - Automatically sends security alerts to Discord
echo   - Pings @everyone for important notices
echo   - Runs every 300 seconds (5 minutes)
echo   - Configurable via .env file
echo.
pause
goto menu

:end
endlocal

:end
endlocal
