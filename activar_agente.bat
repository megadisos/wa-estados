@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0activar_agente.ps1" %*
pause
