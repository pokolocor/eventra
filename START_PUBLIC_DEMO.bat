@echo off
setlocal
cd /d "%~dp0"
set "WINGET_LINKS=%LOCALAPPDATA%\Microsoft\WinGet\Links"

where cloudflared >nul 2>nul
if errorlevel 1 (
  if exist "%WINGET_LINKS%\cloudflared.exe" (
    set "PATH=%PATH%;%WINGET_LINKS%"
  ) else (
    echo [1/2] cloudflared not found - installing it once via winget...
    winget install --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements
    if exist "%WINGET_LINKS%\cloudflared.exe" set "PATH=%PATH%;%WINGET_LINKS%"
  )
)

echo.
echo ============================================================
echo   EVENTRA - PUBLIC DEMO LINK
echo   Make sure the Eventra server is running first:
echo   double-click START_EVENTRA_DEMO.bat in ANOTHER window.
echo ============================================================
echo.
echo [2/2] Starting public tunnel...
echo A link like  https://abcd-1234.trycloudflare.com  will appear below.
echo Share THAT link - anyone, on any network, can open it.
echo Keep BOTH windows open while you demo.
echo.
cloudflared tunnel --url http://localhost:8000
echo.
echo Tunnel closed. Press any key to exit.
pause >nul