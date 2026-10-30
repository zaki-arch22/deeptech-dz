@echo off
cd /d "%~dp0"
if not exist settings.txt copy settings.example.txt settings.txt >nul
findstr /r /c:"^BOT_TOKEN=..*" settings.txt >nul || (echo Fill BOT_TOKEN and CHANNEL in settings.txt, save, then run this file again. & notepad settings.txt & exit /b)
findstr /r /c:"^CHANNEL=..*" settings.txt >nul || (echo Fill CHANNEL in settings.txt, save, then run this file again. & notepad settings.txt & exit /b)
docker compose up -d --build
if errorlevel 1 (echo Docker failed - open Docker Desktop, wait until it says Engine running, then try again. & pause & exit /b)
echo Deeptech DZ is running. Send /id to your bot in Telegram.
pause
