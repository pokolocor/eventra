"""Eventra FastAPI application.

    uvicorn backend.main:app --reload --port 8000

If FastAPI/uvicorn are not installed, `python backend/run.py` automatically
falls back to the standard-library dev server (`backend/dev_server.py`), which
exposes the identical JSON contract.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import BACKEND_DIR, settings
from backend.api.routes_agent import router as agent_router
from backend.api.routes_events import router as events_router
from backend.api.routes_portfolio import router as portfolio_router
from backend.api.routes_system import router as system_router
from backend.services.registry import get_registry

STATIC_DIR = BACKEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    registry = get_registry()
    result = registry.bootstrap()
    app.state.registry = registry
    app.state.bootstrap = result
    yield


app = FastAPI(
    title="Eventra API",
    description="From Events to Execution - autonomous event-driven trading agent (paper only).",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(events_router)
app.include_router(agent_router)
app.include_router(portfolio_router)


@app.get("/api", include_in_schema=False)
def api_index() -> Dict[str, Any]:
    return {
        "app": settings.app_name,
        "tagline": settings.tagline,
        "version": settings.version,
        "mode": "PAPER / DEMO" if settings.demo_mode else "PAPER",
        "endpoints": [
            "GET  /api/health",
            "GET  /api/system/status",
            "POST /api/system/kill-switch",
            "POST /api/system/reset",
            "GET  /api/system/audit",
            "GET  /api/market/quotes",
            "GET  /api/events",
            "POST /api/events",
            "POST /api/events/sync",
            "GET  /api/events/templates",
            "GET  /api/agent/templates",
            "POST /api/agent/simulate",
            "POST /api/agent/run",
            "GET  /api/agent/decisions",
            "GET  /api/agent/decisions/{id}",
            "GET  /api/agent/explain/{symbol}",
            "GET  /api/portfolio",
            "GET  /api/portfolio/history",
            "GET  /api/portfolio/trades",
            "GET  /api/portfolio/positions",
        ],
    }


@app.exception_handler(Exception)
async def unhandled(_request: Any, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def terminal() -> Any:
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Demo terminal UI not built yet. Use /docs or /api."})
