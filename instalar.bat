@echo off
REM Instala todo en Windows. Requiere Python 3.10+ (https://www.python.org/downloads/, marca "Add python to PATH").
cd /d "%~dp0"
py -3 -m venv .venv || (echo No se encontro Python. Instalalo desde python.org y vuelve a ejecutar. & pause & exit /b 1)
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
if not exist datos mkdir datos
echo.
echo Listo. Siguientes pasos:
echo   1) login.bat customania     (escanear QR)
echo   2) login.bat personal       (escanear QR)
echo   3) .venv\Scripts\python publicar.py --dry-run
echo   4) .venv\Scripts\python publicar.py --sin-enviar --depurar --forzar --cuenta personal
echo   5) activar_tarea.bat
pause
