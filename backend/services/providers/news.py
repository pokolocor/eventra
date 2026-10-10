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
    def fetch_events(
        self, limit: int = 25, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Return normalised event dicts, newest first."""


class DemoNewsProvider(NewsProvider):
    """Deterministic seeded firehose used for Demo Mode and offline hacking."""

    name = "demo"

    def __init__(self, seed_events: Optional[List[Dict[str, Any]]] = None) -> None:
        self.seed_events = seed_events if seed_events is not None else SEEDED_EVENTS

    def fetch_events(
        self, limit: int = 25, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
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

    def __init__(
        self,
        url: str,
        token: str = "",
        timeout: float = 10.0,
        items_key: str = "results",
    ) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout
        self.items_key = items_key

    def fetch_events(
        self, limit: int = 25, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        request = urllib.request.Request(
            self.url, headers={"Accept": "application/json"}
        )
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
        raw_ts = (
            item.get("published_at") or item.get("datetime") or item.get("timestamp")
        )
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


class FinnhubNewsProvider(NewsProvider):
    """Live financial news from Finnhub (free tier: 60 calls/min).

    Get your API key at https://finnhub.io/
    Configure with FINNHUB_API_KEY environment variable.
    """

    name = "finnhub"
    BASE_URL = "https://finnhub.io/api/v1/news"

    # Map Finnhub categories to Eventra categories
    CATEGORY_MAP = {
        "general": "other",
        "forex": "macro",
        "crypto": "crypto_regulation",
        "merger": "earnings",
        "press-release": "other",
        "earnings": "earnings",
    }

    def __init__(
        self, api_key: str, category: str = "general", timeout: float = 10.0
    ) -> None:
        self.api_key = api_key
        self.category = category
        self.timeout = timeout

    def fetch_events(
        self, limit: int = 25, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        params = f"category={self.category}&token={self.api_key}"
        url = f"{self.BASE_URL}?{params}"

        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            urllib.error.HTTPError,
        ):
            return []

        if not isinstance(payload, list):
            return []

        events: List[Dict[str, Any]] = []
        for item in payload:
            mapped = self._map_item(item)
            if mapped is None:
                continue
            timestamp = mapped["timestamp"]
            if since is not None and timestamp < since:
                continue
            events.append(mapped)
            if len(events) >= limit:
                break

        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events

    def _map_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = str(item.get("headline") or "").strip()
        if not title:
            return None

        # Parse timestamp (Finnhub uses Unix timestamp)
        raw_ts = item.get("datetime")
        try:
            timestamp = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            timestamp = datetime.now(timezone.utc)

        # Extract tickers from related field
        related = item.get("related") or ""
        tickers = [t.strip().upper() for t in related.split(",") if t.strip()]

        # Map category
        finnhub_cat = str(item.get("category") or "general").lower()
        eventra_cat = self.CATEGORY_MAP.get(finnhub_cat, "other")

        # Determine importance based on source and content
        source = str(item.get("source") or "unknown")
        summary = str(item.get("summary") or "")
        importance = "medium"
        if any(
            kw in title.lower()
            for kw in ["fed", "fomc", "cpi", "gdp", "jobs", "inflation"]
        ):
            importance = "high"
        elif any(kw in title.lower() for kw in ["earnings", "revenue", "profit"]):
            importance = "medium"

        return {
            "id": _stable_id(title, source),
            "timestamp": timestamp.isoformat(),
            "title": title,
            "source": source,
            "category": eventra_cat,
            "summary": summary,
            "affected_assets": tickers[:5],  # Limit to top 5
            "importance": importance,
            "raw": item,
            "is_simulated": False,
        }
