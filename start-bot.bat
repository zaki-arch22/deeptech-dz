@echo off
cd /d "%~dp0"
if not exist settings.txt (
  copy settings.example.txt settings.txt >nul
  echo املأ settings.txt ثم شغّل هذا الملف مرة أخرى.
  notepad settings.txt
  exit /b
)
docker compose up -d --build
echo Deeptech DZ يعمل. السجل: docker logs -f deeptech-dz
pause
