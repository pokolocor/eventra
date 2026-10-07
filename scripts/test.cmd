@echo off
REM Eventra test runner - works with or without pytest installed.
setlocal
cd /d "%~dp0\.."
set PYTHONPATH=%CD%
if defined PYTHON_BIN (%PYTHON_BIN% backend\run_tests.py %*) else (python backend\run_tests.py %*)
endlocal
