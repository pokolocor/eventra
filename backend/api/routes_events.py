"""Event ingestion endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from backend.api import handlers
from backend.api.deps import registry
from backend.schemas.api import IngestEventRequest

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=None)
def get_events(limit: int = Query(40, ge=1, le=200)) -> List[Dict[str, Any]]:
    return handlers.list_events(registry(), limit=limit)


@router.post("/sync", response_model=None)
def post_sync(limit: int = Query(40, ge=1, le=200)) -> Dict[str, Any]:
    return handlers.sync_events(registry(), limit=limit)


@router.post("", response_model=None, status_code=201)
def post_event(payload: IngestEventRequest) -> Dict[str, Any]:
    data = payload.model_dump(mode="json", exclude_none=True)
    return handlers.run_event_payload(registry(), data)


@router.get("/templates", response_model=None)
def get_templates() -> List[Dict[str, Any]]:
    return handlers.list_templates(registry())


@router.get("/{event_id}", response_model=None)
def get_event(event_id: str) -> Dict[str, Any]:
    event = registry().events.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Unknown event {event_id}")
    return event.model_dump(mode="json")
