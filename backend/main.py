"""Eventra FastAPI application."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.config import BACKEND_DIR, settings
from backend.api.routes_agent import router as agent_router
from backend.api.routes_events import router as events_router
from backend.api.routes_portfolio import router as portfolio_router
from backend.api.routes_system import router as system_router
from backend.services.registry import get_registry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

STATIC_DIR = BACKEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    registry = get_registry()
    result = registry.bootstrap()
    app.state.registry = registry
    app.state.bootstrap = result

    logger.info(
        f"Eventra started | mode={'demo' if settings.demo_mode else 'production'} | "
        f"llm={'qwen' if settings.qwen_available else 'demo-mock'} | "
        f"db={settings.database_url}"
    )

    yield


app = FastAPI(
    title="Eventra API",
    description="From Events to Execution - autonomous event-driven trading agent (paper only).",
    version=settings.version,
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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
            "GET  /api/ready",
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
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")

    if settings.demo_mode:
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(exc).__name__}: {exc}", "request_id": request_id}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id}
        )

if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")