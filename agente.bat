@echo off
REM Corre el agente de la app en esta ventana (para probar). Para dejarlo fijo usa activar_agente.bat
cd /d "%~dp0"
.venv\Scripts\python agente.py %*
pause
