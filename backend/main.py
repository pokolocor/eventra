"""Eventra FastAPI application."""

from __future__ import annotations

import asyncio
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
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

STATIC_DIR = BACKEND_DIR / "static"

# Auto-sync interval in seconds (5 minutes)
AUTO_SYNC_INTERVAL = 300


async def auto_sync_and_analyze() -> None:
    """Background task to periodically sync live events and auto-analyze pending ones."""
    while True:
        try:
            await asyncio.sleep(AUTO_SYNC_INTERVAL)
            registry = get_registry()

            # Only sync if using a live provider (not demo)
            if registry.news.name != "demo":
                fresh = registry.events.sync(limit=20)
                if fresh:
                    logger.info(
                        f"Auto-sync: {len(fresh)} new events from {registry.news.name}"
                    )

            # Auto-analyze pending events (limit to 3 per cycle to avoid overwhelming Qwen)
            # Get all events and check which ones don't have decisions yet
            all_events = registry.events.list_events(limit=100)
            pending_events = []
            for event in all_events:
                # Check if this event has been analyzed
                decisions = registry.repository.list_decisions(limit=500)
                has_decision = any(d.event.id == event.id for d in decisions)
                if not has_decision:
                    pending_events.append(event)

            analyzed = 0
            for event in pending_events[:3]:  # Max 3 per cycle
                try:
                    # Run the agent on this event
                    run = registry.orchestrator.run_sync(
                        event_payload=event.model_dump(mode="json")
                    )
                    if run.status == "completed":
                        analyzed += 1
                        logger.info(
                            f"Auto-analyzed event {event.id}: {run.status}, {len(run.trades)} trades"
                        )
                    await asyncio.sleep(2)  # Brief pause between analyses
                except Exception as exc:
                    logger.warning(f"Auto-analysis failed for event {event.id}: {exc}")

            if analyzed > 0:
                logger.info(f"Auto-analysis cycle: {analyzed} events processed")

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"Auto-sync/analyze failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    registry = get_registry()
    result = registry.bootstrap()
    app.state.registry = registry
    app.state.bootstrap = result

    # Start auto-sync task if using live news provider
    sync_task = None
    if registry.news.name != "demo":
        sync_task = asyncio.create_task(auto_sync_and_analyze())
        logger.info(
            f"Auto-sync enabled: fetching live events from {registry.news.name} every {AUTO_SYNC_INTERVAL}s"
        )

    logger.info(
        f"Eventra started | mode={'demo' if settings.demo_mode else 'production'} | "
        f"llm={'qwen' if settings.qwen_available else 'demo-mock'} | "
        f"news={registry.news.name} | db={settings.database_url}"
    )

    # Initial sync on startup for live providers
    if registry.news.name != "demo":
        try:
            fresh = registry.events.sync(limit=20)
            logger.info(f"Initial sync: {len(fresh)} events from {registry.news.name}")
        except Exception as exc:
            logger.warning(f"Initial sync failed: {exc}")

    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass


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
            content={
                "detail": f"{type(exc).__name__}: {exc}",
                "request_id": request_id,
            },
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )


if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
