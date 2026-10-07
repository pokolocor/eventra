"""Shared FastAPI dependencies."""

from __future__ import annotations

from backend.services.registry import ServiceRegistry, get_registry


def registry() -> ServiceRegistry:
    return get_registry()
