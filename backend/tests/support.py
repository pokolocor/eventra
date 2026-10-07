"""Shared helpers so the suite runs under pytest *and* the bundled runner.

Nothing here needs pytest fixtures, which keeps `python backend/run_tests.py`
working on a machine with no test dependencies installed.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config import Settings, RiskLimits
from backend.database.repository import JsonFileRepository
from backend.models.domain import Event, EventCategory, Importance
from backend.services.registry import ServiceRegistry


def make_settings(tmp: Path, **overrides: Any) -> Settings:
    settings = Settings(
        qwen_api_key=overrides.pop("qwen_api_key", ""),
        demo_mode=True,
        paper_trading_only=True,
        data_dir=tmp,
        database_url="sqlite:///./unused.db",
        risk_limits=overrides.pop("risk_limits", RiskLimits()),
    )
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def make_registry(
    tmp: Optional[Path] = None,
    settings: Optional[Settings] = None,
    seed: bool = True,
) -> ServiceRegistry:
    tmp = Path(tmp) if tmp else Path(tempfile.mkdtemp(prefix="eventra-test-"))
    tmp.mkdir(parents=True, exist_ok=True)
    settings = settings or make_settings(tmp)
    repository = JsonFileRepository(tmp / "state.json")
    registry = ServiceRegistry(settings=settings, repository=repository)
    if seed:
        registry.bootstrap()
    return registry


def cleanup(registry: ServiceRegistry) -> None:
    repository = registry.repository
    if isinstance(repository, JsonFileRepository):
        shutil.rmtree(repository.path.parent, ignore_errors=True)


def make_event(
    title: str = "Test event",
    category: EventCategory = EventCategory.MACRO,
    importance: Importance = Importance.HIGH,
    assets: Optional[list] = None,
    summary: str = "Synthetic event used by the Eventra test-suite.",
    template_key: Optional[str] = None,
) -> Event:
    from datetime import datetime, timezone

    return Event(
        id=f"evt_test_{abs(hash(title)) % 10**10}",
        timestamp=datetime.now(timezone.utc),
        title=title,
        source="unit-test",
        category=category,
        summary=summary,
        affected_assets=assets or ["SPY"],
        importance=importance,
        template_key=template_key,
    )


def run_template(registry: ServiceRegistry, key: str) -> Any:
    return registry.orchestrator.run_sync(template_key=key)


def portfolio_dict(registry: ServiceRegistry) -> Dict[str, Any]:
    from backend.api import handlers

    return handlers.portfolio_view(registry)
