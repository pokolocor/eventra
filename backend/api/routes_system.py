"""System, market data and safety endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.api import handlers
from backend.api.deps import admin_principal, registry
from backend.schemas.api import HealthResponse, KillSwitchRequest
from backend.security import Principal

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> Dict[str, Any]:
    """Liveness: the process is up.

    Deliberately shallow - a store outage must not make Render restart a
    healthy process. `/api/ready` is the probe that gates traffic.
    """

    service = registry()
    try:
        kill_switch = service.repository.get_kill_switch()
    except Exception:  # pragma: no cover - store outage
        kill_switch = False
    return {
        "status": "ok",
        "app": service.settings.app_name,
        "tagline": service.settings.tagline,
        "mode": "PAPER / DEMO" if service.settings.demo_mode else "PAPER",
        "llm_provider": service.llm()[1],
        "kill_switch": kill_switch,
    }


@router.get("/api/ready", response_model=None)
def ready() -> Any:
    """Readiness: can this replica serve traffic (store reachable)?

    Returns 503 when the store is unavailable so Render pulls the instance out
    of rotation instead of serving a broken dashboard.
    """

    payload = handlers.readiness(registry())
    status_code = 200 if payload.get("ready") else 503
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/api/system/status", response_model=None)
def status() -> Dict[str, Any]:
    return handlers.system_status(registry())


@router.post("/api/system/kill-switch", response_model=None)
def kill_switch(
    payload: KillSwitchRequest, principal: Principal = Depends(admin_principal)
) -> Dict[str, Any]:
    return handlers.set_kill_switch(registry(), payload.engaged, principal=principal)


@router.post("/api/system/reset", response_model=None)
def reset(principal: Principal = Depends(admin_principal)) -> Dict[str, Any]:
    return handlers.reset_demo(registry(), principal=principal)


@router.get("/api/system/audit", response_model=None)
def audit(limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return handlers.audit_log(registry(), limit=limit)


@router.get("/api/market/quotes", response_model=None)
def quotes() -> List[Dict[str, Any]]:
    return handlers.market_quotes(registry())


@router.get("/api/metrics", response_model=None)
def metrics() -> Dict[str, Any]:
    """Performance metrics for hackathon submission (Sharpe, drawdown, win rate, etc.)."""
    return handlers.performance_metrics(registry())
