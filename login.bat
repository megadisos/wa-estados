@echo off
REM Vincula una cuenta (una sola vez):  login.bat customania   |   login.bat personal
cd /d "%~dp0"
if "%~1"=="" (echo Uso: login.bat nombre_de_cuenta & exit /b 1)
.venv\Scripts\python login.py %1
pause
