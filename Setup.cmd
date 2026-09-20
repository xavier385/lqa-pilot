@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1" %*
if errorlevel 1 pause
