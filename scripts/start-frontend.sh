#!/usr/bin/env bash
# Start the Next.js dashboard. Requires `npm install` in frontend/.
set -euo pipefail
cd "$(dirname "$0")/../frontend"

if [ ! -d node_modules ]; then
  echo "[eventra] installing frontend dependencies..."
  npm install
fi
exec npm run dev
