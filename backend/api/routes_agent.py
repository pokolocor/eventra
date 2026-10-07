"""Agent decision pipeline endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from backend.api import handlers
from backend.api.deps import registry
from backend.schemas.api import DecisionStarted, SimulateEventRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/templates", response_model=None)
def get_templates() -> List[Dict[str, Any]]:
    return handlers.list_templates(registry())


@router.post("/simulate", response_model=DecisionStarted, status_code=202)
def post_simulate(payload: SimulateEventRequest) -> Dict[str, Any]:
    service = registry()
    if payload.template_key not in service.events.template_keys():
        raise HTTPException(status_code=404, detail=f"Unknown template '{payload.template_key}'")
    return handlers.simulate_event(service, payload.template_key)


@router.post("/run", response_model=None)
def post_run(payload: SimulateEventRequest) -> Dict[str, Any]:
    """Synchronous variant - returns the complete decision chain in one call."""

    service = registry()
    if payload.template_key not in service.events.template_keys():
        raise HTTPException(status_code=404, detail=f"Unknown template '{payload.template_key}'")
    return handlers.run_sync(service, template_key=payload.template_key)


@router.get("/decisions", response_model=None)
def get_decisions(limit: int = Query(25, ge=1, le=100)) -> List[Dict[str, Any]]:
    return handlers.list_decisions(registry(), limit=limit)


@router.get("/decisions/{decision_id}", response_model=None)
def get_decision(decision_id: str) -> Dict[str, Any]:
    result = handlers.get_decision(registry(), decision_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown decision {decision_id}")
    return result


@router.get("/explain/{symbol}", response_model=None)
def get_explanation(symbol: str) -> Dict[str, Any]:
    return handlers.explain_symbol(registry(), symbol)
