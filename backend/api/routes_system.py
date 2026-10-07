"""System, market data and safety endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from backend.api import handlers
from backend.api.deps import registry
from backend.schemas.api import HealthResponse, KillSwitchRequest

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> Dict[str, Any]:
    service = registry()
    return {
        "status": "ok",
        "app": service.settings.app_name,
        "tagline": service.settings.tagline,
        "mode": "PAPER / DEMO" if service.settings.demo_mode else "PAPER",
        "llm_provider": service.llm()[1],
        "kill_switch": service.repository.get_kill_switch(),
    }


@router.get("/api/system/status", response_model=None)
def status() -> Dict[str, Any]:
    return handlers.system_status(registry())


@router.post("/api/system/kill-switch", response_model=None)
def kill_switch(payload: KillSwitchRequest) -> Dict[str, Any]:
    return handlers.set_kill_switch(registry(), payload.engaged)


@router.post("/api/system/reset", response_model=None)
def reset() -> Dict[str, Any]:
    return handlers.reset_demo(registry())


@router.get("/api/system/audit", response_model=None)
def audit(limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return handlers.audit_log(registry(), limit=limit)


@router.get("/api/market/quotes", response_model=None)
def quotes() -> List[Dict[str, Any]]:
    return handlers.market_quotes(registry())
