"""Eventra launcher.

Prefers the real FastAPI + uvicorn stack. When those packages are missing (for
example in an offline demo environment) it transparently falls back to the
standard-library dev server, which serves the same API and the same UI.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    host = "127.0.0.1"
    port = 8000
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg in {"--host"} and index + 1 < len(argv):
            host = argv[index + 1]
        if arg in {"--port"} and index + 1 < len(argv):
            port = int(argv[index + 1])

    try:
        import uvicorn  # noqa: F401
        from backend.main import app  # noqa: F401
    except ImportError as exc:
        print(f"[eventra] FastAPI stack unavailable ({exc}).")
        print("[eventra] Starting the zero-dependency dev server instead.")
        from backend.dev_server import main as dev_main

        return dev_main(["--host", host, "--port", str(port)])

    import uvicorn

    print(f"[eventra] Starting FastAPI on http://{host}:{port}")
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
