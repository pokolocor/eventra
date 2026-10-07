"""Paper portfolio endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from backend.api import handlers
from backend.api.deps import registry

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=None)
def get_portfolio() -> Dict[str, Any]:
    return handlers.portfolio_view(registry())


@router.get("/history", response_model=None)
def get_history(limit: int = Query(240, ge=10, le=2000)) -> List[Dict[str, Any]]:
    return handlers.equity_curve(registry(), limit=limit)


@router.get("/trades", response_model=None)
def get_trades(limit: int = Query(100, ge=1, le=1000)) -> List[Dict[str, Any]]:
    return handlers.trade_history(registry(), limit=limit)


@router.get("/positions", response_model=None)
def get_positions() -> List[Dict[str, Any]]:
    return handlers.portfolio_view(registry())["positions"]
