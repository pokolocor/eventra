# Start the Eventra backend (FastAPI when installed, stdlib server otherwise).
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$env:PYTHONPATH = $projectRoot
& $python "backend\run.py" --host "127.0.0.1" --port 8000
