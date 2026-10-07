"""Demo data seeding.

Creates a believable starting book, a 60-step price history and a populated
event feed so Eventra is presentable the second it boots - no external API
required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.database.state import PortfolioState
from backend.models.domain import Position
from backend.services.providers.market_data import UNIVERSE

SEED_TICK = 60
ENTRY_TICK = 18

# Target weights at seed time. The remainder stays in cash.
ALLOCATIONS: Dict[str, float] = {
    "QQQ": 0.15,
    "SPY": 0.13,
    "BTC": 0.10,
    "NVDA": 0.06,
    "TLT": 0.06,
    "GLD": 0.05,
    "MSFT": 0.04,
    "IWM": 0.03,
    "JPM": 0.03,
}

SEED_CONVICTION: Dict[str, float] = {
    "QQQ": 0.72,
    "SPY": 0.65,
    "BTC": 0.58,
    "NVDA": 0.81,
    "TLT": 0.44,
    "GLD": 0.52,
    "MSFT": 0.68,
    "IWM": 0.49,
    "JPM": 0.61,
}

CRYPTO = {"BTC", "ETH"}


def _price_at(market: Any, symbol: str, tick: int) -> float:
    path = market.history(symbol, points=max(tick, 1) + 1)
    if not path:
        return UNIVERSE[symbol].base_price
    index = min(tick, len(path) - 1)
    return float(path[index]["price"])


def is_seeded(registry: Any) -> bool:
    repository = registry.repository
    if hasattr(repository, "seeded") and repository.seeded:
        return True
    state = repository.load_portfolio()
    return bool(state.positions) and state.starting_balance > 0


def build_starting_portfolio(registry: Any) -> PortfolioState:
    settings = registry.settings
    market = registry.market
    now = datetime.now(timezone.utc)

    for _ in range(SEED_TICK):
        market.advance_tick()
    registry.repository.set_market_tick(SEED_TICK)

    state = PortfolioState(starting_balance=settings.starting_balance, cash=0.0)
    cost = 0.0

    for symbol, weight in ALLOCATIONS.items():
        instrument = UNIVERSE[symbol]
        target_value = settings.starting_balance * weight
        quantity = target_value / instrument.base_price
        quantity = round(quantity, 6) if symbol in CRYPTO else round(quantity, 2)
        entry_price = _price_at(market, symbol, ENTRY_TICK)
        last_price = _price_at(market, symbol, SEED_TICK)
        cost += quantity * entry_price
        state.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            avg_entry_price=round(entry_price, 4),
            last_price=round(last_price, 4),
            conviction=SEED_CONVICTION.get(symbol, 0.5),
            opened_at=now,
            updated_at=now,
        )

    state.cash = round(settings.starting_balance - cost, 2)
    state.realized_pnl = 0.0
    return state


def seed_if_empty(registry: Any) -> Dict[str, Any]:
    if is_seeded(registry):
        return {"seeded": False}

    repository = registry.repository
    state = build_starting_portfolio(registry)

    snapshot = PortfolioState.from_dict(state.to_dict())
    repository.save_portfolio(snapshot)

    events: List[Any] = registry.events.seed_history()
    registry.portfolio.seed_equity_history(points=SEED_TICK)
    registry.portfolio.reset_day_baseline()
    repository.audit(
        "bootstrap",
        "demo_state_seeded",
        f"positions={len(state.positions)} cash={state.cash:,.2f} events={len(events)}",
    )
    if hasattr(repository, "mark_seeded"):
        repository.mark_seeded()

    return {
        "seeded": True,
        "positions": len(state.positions),
        "cash": state.cash,
        "events": len(events),
        "market_tick": SEED_TICK,
    }
