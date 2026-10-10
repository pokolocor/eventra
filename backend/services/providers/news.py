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


class GDELTNewsProvider(NewsProvider):
    """Free global events from GDELT Project (no API key required).

    GDELT monitors news from every country in 100+ languages and identifies
    the people, locations, and themes that drive global events.
    Website: https://www.gdeltproject.org/
    """

    name = "gdelt"
    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    # Map GDELT themes to Eventra categories
    THEME_MAP = {
        "ECON": "macro",
        "FINANCE": "macro",
        "POL": "geopolitical",
        "GOV": "geopolitical",
        "CRIME": "other",
        "PROTEST": "geopolitical",
        "WAR": "geopolitical",
        "HEALTH": "other",
        "ENV": "commodity",
        "ENERGY": "commodity",
        "TECH": "other",
    }

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def fetch_events(
        self, limit: int = 25, since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        # Query for recent financial/economic news
        from urllib.parse import urlencode

        query = "finance OR economy OR market OR fed OR inflation OR earnings"
        params = urlencode(
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": min(limit, 50),
                "timespan": "1d",
                "sort": "datedesc",
            }
        )
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

        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            return []

        events: List[Dict[str, Any]] = []
        for item in articles:
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
        title = str(item.get("title") or "").strip()
        if not title:
            return None

        # Parse timestamp
        raw_ts = item.get("seendate") or item.get("date")
        try:
            # GDELT format: 20261010T120000Z
            if raw_ts and len(raw_ts) >= 15:
                timestamp = datetime.strptime(raw_ts[:15], "%Y%m%dT%H%M%S")
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)
        except (TypeError, ValueError):
            timestamp = datetime.now(timezone.utc)

        # Extract source
        source = str(item.get("domain") or item.get("source") or "unknown")

        # Determine category from themes
        themes = item.get("theme") or []
        if isinstance(themes, str):
            themes = [themes]

        eventra_cat = "other"
        for theme in themes:
            theme_upper = theme.upper()
            for key, value in self.THEME_MAP.items():
                if key in theme_upper:
                    eventra_cat = value
                    break
            if eventra_cat != "other":
                break

        # Determine importance
        summary = str(item.get("summary") or "")
        importance = "medium"
        title_lower = title.lower()
        if any(
            kw in title_lower
            for kw in ["fed", "fomc", "cpi", "gdp", "jobs", "inflation", "rate"]
        ):
            importance = "high"
        elif any(kw in title_lower for kw in ["market", "stock", "bond", "crypto"]):
            importance = "medium"

        # Try to extract mentioned assets
        assets = []
        # Look for common tickers in title
        ticker_patterns = [
            "AAPL",
            "GOOGL",
            "MSFT",
            "AMZN",
            "TSLA",
            "NVDA",
            "META",
            "SPY",
            "QQQ",
            "BTC",
            "ETH",
        ]
        for ticker in ticker_patterns:
            if ticker in title.upper():
                assets.append(ticker)

        return {
            "id": _stable_id(title, source),
            "timestamp": timestamp.isoformat(),
            "title": title,
            "source": source,
            "category": eventra_cat,
            "summary": summary[:500] if summary else "",
            "affected_assets": assets[:5],
            "importance": importance,
            "raw": item,
            "is_simulated": False,
        }
