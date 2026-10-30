@echo off
cd /d "%~dp0"
docker logs --tail 80 -f deeptech-dz
