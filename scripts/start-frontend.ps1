# Start the Eventra Next.js dashboard.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot "frontend")

if (-not (Test-Path "node_modules")) {
  Write-Host "[eventra] installing frontend dependencies..."
  npm install
}
npm run dev
