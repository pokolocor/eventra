"""Composition root.

Builds every service once and wires them together. Both the FastAPI app and the
zero-dependency dev server use this, so there is exactly one object graph and
one source of truth for state.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

from backend.config import Settings, load_settings
from backend.database.repository import Repository, create_repository
from backend.database.seed import seed_if_empty
from backend.security import Guard
from backend.services.demo_llm import DemoLLMService
from backend.services.event_service import EventService
from backend.services.execution_service import ExecutionService
from backend.services.portfolio_service import PortfolioService
from backend.services.providers.bitget import BitgetDemoService
from backend.services.providers.market_data import (
    DemoMarketDataProvider,
    MarketDataProvider,
)
from backend.services.providers.news import (
    DemoNewsProvider,
    HttpNewsProvider,
    NewsProvider,
)
from backend.services.qwen_service import QwenService
from backend.services.risk_engine import RiskEngine


def build_market_provider(
    settings: Settings, repository: Repository
) -> MarketDataProvider:
    provider = DemoMarketDataProvider()
    stored = int(repository.load_system().market_tick or 0)
    # Persisted state wins; `MARKET_TICK` is only the cold-start position.
    provider.tick = max(0, stored if stored else int(settings.market_tick or 0))
    return provider


def build_news_provider(settings: Settings) -> NewsProvider:
    url = os.environ.get("EVENTRA_NEWS_URL", "").strip()
    if url:
        return HttpNewsProvider(
            url=url,
            token=os.environ.get("EVENTRA_NEWS_TOKEN", "").strip(),
            items_key=os.environ.get("EVENTRA_NEWS_ITEMS_KEY", "results"),
        )
    return DemoNewsProvider()


class ServiceRegistry:
    """Owns the Eventra object graph."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        repository: Optional[Repository] = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.repository = repository or create_repository(self.settings)
        self.guard = Guard(self.settings)
        self.market = build_market_provider(self.settings, self.repository)
        self.news = build_news_provider(self.settings)

        self.events = EventService(self.repository, self.news)
        self.portfolio = PortfolioService(self.repository, self.market, self.settings)
        self.risk_engine = RiskEngine(
            self.settings, self.portfolio, self.market, self.repository
        )
        self.bitget = BitgetDemoService(self.settings)
        self.execution = ExecutionService(
            self.portfolio,
            self.market,
            self.repository,
            self.settings,
            bitget=self.bitget,
        )

        self.qwen = QwenService(self.settings)
        self.demo_llm = DemoLLMService()
        self._orchestrator: Optional[Any] = None
        self._lock = threading.RLock()
        self._bootstrapped = False

    # --- LLM selection ---------------------------------------------------
    def llm(self) -> Tuple[Any, str]:
        """Return (service, mode). Qwen first; Demo Mode only when unavailable."""

        if self.qwen.available:
            return self.qwen, "qwen"
        return self.demo_llm, "demo"

    # --- orchestrator ----------------------------------------------------
    @property
    def orchestrator(self) -> Any:
        from backend.services.agent_orchestrator import AgentOrchestrator

        with self._lock:
            if self._orchestrator is None:
                self._orchestrator = AgentOrchestrator(
                    events=self.events,
                    portfolio=self.portfolio,
                    risk_engine=self.risk_engine,
                    execution=self.execution,
                    repository=self.repository,
                    settings=self.settings,
                    llm_resolver=self.llm,
                )
            return self._orchestrator

    # --- lifecycle -------------------------------------------------------
    def bootstrap(self) -> Dict[str, Any]:
        """Seed demo data on first run. Idempotent."""

        with self._lock:
            if self._bootstrapped:
                return {"seeded": False}
            result = seed_if_empty(self)
            self._bootstrapped = True
            return result

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self.repository.reset()
            self.market.tick = 0
            self._bootstrapped = False
            # Drop the orchestrator so in-flight/in-memory runs cannot survive a reset.
            self._orchestrator = None
            result = self.bootstrap()
            result["reset"] = True
            return result


_registry: Optional[ServiceRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> ServiceRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ServiceRegistry()
            _registry.bootstrap()
        return _registry


def reset_registry() -> None:
    """Used by tests to build a fresh object graph."""

    global _registry
    with _registry_lock:
        _registry = None
