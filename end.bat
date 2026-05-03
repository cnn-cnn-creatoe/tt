@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_service.ps1" -ProjectDir "%~dp0." -Port 5000
exit /b %ERRORLEVEL%
