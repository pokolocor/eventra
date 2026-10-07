"""Event ingestion engine.

Normalises events from any `NewsProvider`, persists them, and builds the
synthetic events behind the dashboard's "Simulate Event" button.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.database.repository import Repository
from backend.models.domain import Event, EventCategory, Importance
from backend.services.providers.event_templates import (
    EVENT_TEMPLATES,
    SEEDED_EVENTS,
    TEMPLATE_ORDER,
    EventTemplate,
)
from backend.services.providers.news import DemoNewsProvider, NewsProvider


def _stable_id(*parts: str) -> str:
    return "evt_" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _coerce_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class EventService:
    def __init__(self, repository: Repository, provider: Optional[NewsProvider] = None) -> None:
        self.repository = repository
        self.provider = provider or DemoNewsProvider()

    # --- catalogue ------------------------------------------------------
    def templates(self) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for key in TEMPLATE_ORDER:
            template = EVENT_TEMPLATES[key]
            grouped.setdefault(template.group, []).append(template.to_dict())
        return [{"group": name, "templates": items} for name, items in grouped.items()]

    def template_keys(self) -> List[str]:
        return list(TEMPLATE_ORDER)

    def get_template(self, key: str) -> Optional[EventTemplate]:
        return EVENT_TEMPLATES.get(key)

    # --- ingestion ------------------------------------------------------
    def sync(self, limit: int = 40) -> List[Event]:
        """Pull the latest events from the configured provider."""

        raw_items = self.provider.fetch_events(limit=limit)
        known = {event.id for event in self.repository.list_events(limit=500)}
        fresh: List[Event] = []
        for item in raw_items:
            event = self.normalise(item)
            if event.id in known:
                continue
            self.repository.save_event(event)
            self.repository.audit("event_service", "event_ingested", f"{event.id} :: {event.title[:80]}")
            fresh.append(event)
        return fresh

    def normalise(self, payload: Dict[str, Any]) -> Event:
        data = dict(payload)
        title = str(data.get("title", "")).strip()
        source = str(data.get("source", "unknown")).strip() or "unknown"
        data["id"] = str(data.get("id") or _stable_id(title, source))
        data["timestamp"] = _coerce_timestamp(data.get("timestamp"))
        data.setdefault("category", EventCategory.OTHER.value)
        data.setdefault("importance", Importance.MEDIUM.value)
        data.setdefault("summary", "")
        data.setdefault("affected_assets", [])
        data.setdefault("raw", {})
        data["raw"] = {**data["raw"], "provider": self.provider.name}
        return Event.model_validate(data)

    def list_events(self, limit: int = 50) -> List[Event]:
        return self.repository.list_events(limit=limit)

    def get_event(self, event_id: str) -> Optional[Event]:
        return self.repository.get_event(event_id)

    # --- simulation -----------------------------------------------------
    def simulate(self, template_key: str, when: Optional[datetime] = None) -> Tuple[Event, EventTemplate]:
        template = EVENT_TEMPLATES.get(template_key)
        if template is None:
            raise KeyError(f"Unknown event template: {template_key}")

        timestamp = when or datetime.now(timezone.utc)
        event = Event(
            id=_stable_id(template.key, timestamp.isoformat(), uuid.uuid4().hex),
            timestamp=timestamp,
            title=template.title,
            source=template.source,
            category=EventCategory(template.category),
            summary=template.summary,
            affected_assets=list(template.affected_assets),
            importance=Importance(template.importance),
            raw={
                "provider": "eventra-simulator",
                "template_key": template.key,
                "label": template.label,
                "group": template.group,
                "expected_analysis_keys": sorted(template.expected_analysis.keys()),
            },
            template_key=template.key,
            is_simulated=True,
        )
        self.repository.save_event(event)
        self.repository.audit(
            "event_service", "event_simulated", f"{template.key} -> {event.id}"
        )
        return event, template

    def seed_history(self, minutes_ago: Optional[int] = None) -> List[Event]:
        """Seed the bundled historical events (idempotent)."""

        now = datetime.now(timezone.utc)
        created: List[Event] = []
        for item in SEEDED_EVENTS:
            offset = minutes_ago if minutes_ago is not None else int(item.get("minutes_ago", 0))
            payload = dict(item)
            payload["timestamp"] = (now - timedelta(minutes=offset)).isoformat()
            event = self.normalise(payload)
            if self.repository.get_event(event.id) is not None:
                continue
            self.repository.save_event(event)
            created.append(event)
        if created:
            self.repository.audit("event_service", "events_seeded", f"{len(created)} historical events")
        return created
