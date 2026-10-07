@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHONPATH=%ROOT%"
set "PY=C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
echo ============================================================
echo   EVENTRA - From Events to Execution   (PAPER / DEMO)
echo   Dashboard:  http://127.0.0.1:8000/ui/
echo   Same Wi-Fi: http://YOUR-PC-IP:8000/ui/   (find IP with: ipconfig)
echo   Keep this window OPEN while you demo. Close it to stop.
echo ============================================================
echo.
"%PY%" backend\run.py --host 0.0.0.0 --port 8000
echo.
echo Server stopped. Press any key to close this window.
pause >nul