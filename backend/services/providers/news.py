"""News / event ingestion providers.

`NewsProvider` is the only contract the event engine depends on. Swap in a real
vendor (Benzinga, Polygon, NewsAPI, Finnhub, RSS, an exchange calendar feed) by
implementing `fetch_events` - nothing else in Eventra has to change.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.services.providers.event_templates import SEEDED_EVENTS


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


class NewsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch_events(self, limit: int = 25, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Return normalised event dicts, newest first."""


class DemoNewsProvider(NewsProvider):
    """Deterministic seeded firehose used for Demo Mode and offline hacking."""

    name = "demo"

    def __init__(self, seed_events: Optional[List[Dict[str, Any]]] = None) -> None:
        self.seed_events = seed_events if seed_events is not None else SEEDED_EVENTS

    def fetch_events(self, limit: int = 25, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        events: List[Dict[str, Any]] = []
        for item in self.seed_events:
            timestamp = now - timedelta(minutes=float(item.get("minutes_ago", 0)))
            if since is not None and timestamp < since:
                continue
            events.append(
                {
                    "id": _stable_id(item["title"], item["source"]),
                    "timestamp": timestamp.isoformat(),
                    "title": item["title"],
                    "source": item["source"],
                    "category": item.get("category", "other"),
                    "summary": item.get("summary", ""),
                    "affected_assets": list(item.get("affected_assets", [])),
                    "importance": item.get("importance", "medium"),
                    "raw": {"provider": self.name, **item},
                    "is_simulated": False,
                }
            )
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]


class HttpNewsProvider(NewsProvider):
    """Reference implementation for a JSON news API.

    Configure with `EVENTRA_NEWS_URL` (and optionally `EVENTRA_NEWS_TOKEN`).
    The response mapper is intentionally tiny - adapt `_map_item` to the vendor
    you plug in.
    """

    name = "http"

    def __init__(self, url: str, token: str = "", timeout: float = 10.0, items_key: str = "results") -> None:
        self.url = url
        self.token = token
        self.timeout = timeout
        self.items_key = items_key

    def fetch_events(self, limit: int = 25, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        request = urllib.request.Request(self.url, headers={"Accept": "application/json"})
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return []

        items = payload.get(self.items_key) if isinstance(payload, dict) else payload
        events: List[Dict[str, Any]] = []
        for item in items or []:
            mapped = self._map_item(item)
            if mapped is None:
                continue
            timestamp = mapped["timestamp"]
            if since is not None and timestamp < since:
                continue
            events.append(mapped)
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    def _map_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            return None
        raw_ts = item.get("published_at") or item.get("datetime") or item.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return {
            "id": _stable_id(title, str(item.get("source", "unknown"))),
            "timestamp": timestamp.isoformat(),
            "title": title,
            "source": str(item.get("source") or "unknown"),
            "category": str(item.get("category") or "other"),
            "summary": str(item.get("summary") or item.get("description") or ""),
            "affected_assets": item.get("tickers") or item.get("symbols") or [],
            "importance": str(item.get("importance") or "medium"),
            "raw": item,
            "is_simulated": False,
        }
