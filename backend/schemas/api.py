"""Request/response schemas for the Eventra HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.domain import EventCategory, Importance


class SimulateEventRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    template_key: str = Field(min_length=1, description="Key from GET /api/agent/templates")


class IngestEventRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=3, max_length=300)
    source: str = Field(default="manual", min_length=1, max_length=120)
    category: EventCategory = EventCategory.OTHER
    summary: str = Field(default="", max_length=4000)
    affected_assets: List[str] = Field(default_factory=list)
    importance: Importance = Importance.MEDIUM
    timestamp: Optional[datetime] = None
    raw: Dict[str, Any] = Field(default_factory=dict)
    template_key: Optional[str] = None

    @field_validator("affected_assets", mode="before")
    @classmethod
    def _norm(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [v.strip().upper() for v in value.split(",") if v.strip()]
        return [str(v).strip().upper() for v in (value or [])]


class KillSwitchRequest(BaseModel):
    engaged: bool = True


class DecisionStarted(BaseModel):
    decision_id: str
    status: str = "running"
    template_key: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "Eventra"
    tagline: str = "From Events to Execution"
    mode: str
    llm_provider: str
    kill_switch: bool
