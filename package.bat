@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_release.ps1" -ProjectDir "%~dp0." -Version "v1.0"
pause
