"""Paper-trading portfolio simulator.

Owns all money maths: average-cost accounting, realised/unrealised PnL,
exposure and the equity curve. It has no opinion about *why* a trade happens -
that is the orchestrator's job - and it never talks to a real broker.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.config import Settings
from backend.database.repository import Repository
from backend.database.state import PortfolioState
from backend.models.domain import (
    EquityPoint,
    Position,
    PortfolioSnapshot,
    Trade,
    TradeAction,
    TradeSide,
    utcnow,
)
from backend.services.providers.market_data import MarketDataProvider


def _round_money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


class InsufficientFundsError(Exception):
    pass


class InsufficientPositionError(Exception):
    pass


class PortfolioService:
    def __init__(
        self,
        repository: Repository,
        market: MarketDataProvider,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.market = market
        self.settings = settings

    # --- reads ----------------------------------------------------------
    def state(self) -> PortfolioState:
        return self.repository.load_portfolio()

    def price_of(self, symbol: str) -> float:
        quote = self.market.quote(symbol)
        if quote is None:
            raise KeyError(f"Unknown instrument: {symbol}")
        return quote.price

    def position(self, symbol: str) -> Optional[Position]:
        return self.state().positions.get(symbol.upper())

    def snapshot(self, persist: bool = True) -> PortfolioSnapshot:
        state = self.state()
        positions: List[Position] = []
        positions_value = 0.0
        unrealized = 0.0

        for symbol, position in sorted(state.positions.items()):
            quote = self.market.quote(symbol)
            if quote is not None:
                position.last_price = quote.price
            if abs(position.quantity) < 1e-9:
                continue
            positions_value += position.market_value
            unrealized += position.unrealized_pnl
            positions.append(position)

        portfolio_value = state.cash + positions_value
        total_pnl = portfolio_value - state.starting_balance
        day_start = state.day_start_value or portfolio_value
        day_pnl = portfolio_value - day_start
        exposure = (positions_value / portfolio_value * 100.0) if portfolio_value else 0.0

        snapshot = PortfolioSnapshot(
            starting_balance=_round_money(state.starting_balance),
            cash=_round_money(state.cash),
            positions=positions,
            positions_value=_round_money(positions_value),
            portfolio_value=_round_money(portfolio_value),
            unrealized_pnl=_round_money(unrealized),
            realized_pnl=_round_money(state.realized_pnl),
            total_pnl=_round_money(total_pnl),
            total_return_pct=round((total_pnl / state.starting_balance) * 100.0, 4)
            if state.starting_balance
            else 0.0,
            day_pnl=_round_money(day_pnl),
            day_pnl_pct=round((day_pnl / day_start) * 100.0, 4) if day_start else 0.0,
            exposure=round(exposure, 4),
            gross_exposure=round(exposure, 4),
            updated_at=utcnow(),
        )

        if persist:
            for position in positions:
                state.positions[position.symbol] = position
            self.repository.save_portfolio(state)
            self.repository.append_equity_point(
                EquityPoint(
                    timestamp=snapshot.updated_at,
                    portfolio_value=snapshot.portfolio_value,
                    cash=snapshot.cash,
                    exposure=snapshot.exposure,
                )
            )
        return snapshot

    def weight_of(self, symbol: str, snapshot: Optional[PortfolioSnapshot] = None) -> float:
        current = snapshot or self.snapshot(persist=False)
        if not current.portfolio_value:
            return 0.0
        position = next((p for p in current.positions if p.symbol == symbol.upper()), None)
        if position is None:
            return 0.0
        return position.market_value / current.portfolio_value * 100.0

    def equity_curve(self, limit: int = 240) -> List[Dict[str, Any]]:
        return [
            {
                "timestamp": point.timestamp.isoformat(),
                "portfolio_value": round(point.portfolio_value, 2),
                "cash": round(point.cash, 2),
                "exposure": round(point.exposure, 2),
            }
            for point in self.repository.list_equity(limit=limit)
        ]

    # --- writes ---------------------------------------------------------
    def target_notional_for(
        self,
        symbol: str,
        action: TradeAction,
        percentage: float,
        snapshot: Optional[PortfolioSnapshot] = None,
    ) -> float:
        """Convert a percentage instruction into a dollar notional."""

        current = snapshot or self.snapshot(persist=False)
        price = self.price_of(symbol)
        percentage = max(0.0, min(100.0, float(percentage)))

        if action in (TradeAction.REDUCE, TradeAction.SELL):
            position = next((p for p in current.positions if p.symbol == symbol.upper()), None)
            base = position.market_value if position else 0.0
            if action == TradeAction.SELL:
                percentage = 100.0
            return base * (percentage / 100.0)

        if action in (TradeAction.INCREASE, TradeAction.BUY, TradeAction.HEDGE):
            base = current.portfolio_value
            return base * (percentage / 100.0)

        return 0.0

    def execute(
        self,
        symbol: str,
        side: TradeSide,
        quantity: float,
        price: float,
        action: TradeAction,
        reason: str = "",
        decision_id: Optional[str] = None,
        event_id: Optional[str] = None,
        fee: float = 0.0,
        slippage: float = 0.0,
        conviction: float = 0.0,
        signal_id: Optional[str] = None,
    ) -> Trade:
        state = self.state()
        symbol = symbol.upper()
        quantity = round(float(quantity), 6)
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")

        notional = quantity * price
        position = state.positions.get(symbol) or Position(symbol=symbol)
        realized = 0.0

        if side == TradeSide.BUY:
            if notional + fee > state.cash + 1e-6:
                raise InsufficientFundsError(
                    f"Not enough cash for {symbol}: need {notional + fee:,.2f}, have {state.cash:,.2f}"
                )
            new_quantity = position.quantity + quantity
            if new_quantity > 0:
                position.avg_entry_price = (
                    position.avg_entry_price * position.quantity + notional
                ) / new_quantity
            position.quantity = new_quantity
            state.cash -= notional + fee
            if position.opened_at is None:
                position.opened_at = utcnow()
        else:
            if position.quantity + 1e-9 < quantity:
                raise InsufficientPositionError(
                    f"Cannot sell {quantity} {symbol}; only {position.quantity} held"
                )
            realized = (price - position.avg_entry_price) * quantity - fee
            position.quantity -= quantity
            state.cash += notional - fee
            state.realized_pnl += realized
            if position.quantity <= 1e-9:
                position.quantity = 0.0
                position.avg_entry_price = 0.0
                position.opened_at = None

        quote = self.market.quote(symbol)
        position.last_price = quote.price if quote else price
        if conviction:
            position.conviction = round(float(conviction), 4)
        if signal_id:
            position.last_signal_id = signal_id
        position.updated_at = utcnow()

        if position.quantity <= 1e-9:
            state.positions.pop(symbol, None)
        else:
            state.positions[symbol] = position

        trade = Trade(
            id=f"trd_{uuid.uuid4().hex[:12]}",
            created_at=utcnow(),
            decision_id=decision_id,
            event_id=event_id,
            symbol=symbol,
            action=action,
            side=side,
            quantity=quantity,
            price=round(price, 4),
            notional=_round_money(notional),
            fee=_round_money(fee),
            slippage=round(slippage, 6),
            realized_pnl=_round_money(realized),
            reason=reason,
            status="FILLED",
            mode="PAPER",
        )

        self.repository.save_portfolio(state)
        self.repository.save_trade(trade)
        self.repository.audit(
            "execution_service",
            f"paper_{side.value.lower()}_{symbol}",
            f"{quantity} @ {price:,.2f} ({action.value}) decision={decision_id}",
        )
        return trade

    def reset_day_baseline(self) -> None:
        snapshot = self.snapshot(persist=False)
        state = self.state()
        state.day_start_value = snapshot.portfolio_value
        self.repository.save_portfolio(state)

    def seed_equity_history(self, points: int = 60) -> None:
        """Rebuild a plausible equity curve from the simulated price paths."""

        state = self.state()
        tick = self.repository.load_system().market_tick
        start = max(0, tick - points)
        series: List[EquityPoint] = []
        base_time = utcnow() - timedelta(minutes=points * 30)

        for offset, step in enumerate(range(start, tick + 1)):
            value = state.cash
            for symbol, position in state.positions.items():
                path = self.market.history(symbol, points=tick + 1)
                if step < len(path):
                    value += position.quantity * path[step]["price"]
            series.append(
                EquityPoint(
                    timestamp=base_time + timedelta(minutes=offset * 30),
                    portfolio_value=_round_money(value),
                    cash=_round_money(state.cash),
                    exposure=round(((value - state.cash) / value) * 100.0, 4) if value else 0.0,
                )
            )

        for point in series:
            self.repository.append_equity_point(point)
        if series:
            state.day_start_value = series[0].portfolio_value
            self.repository.save_portfolio(state)
