"""Paper execution service.

Converts risk-approved actions into simulated fills. It is the only place that
mutates the portfolio, and it refuses to run when the kill switch is engaged.
There is no live-broker code path in this project: paper trading only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.config import Settings
from backend.database.repository import Repository
from backend.models.domain import (
    PortfolioActionProposal,
    RiskDecision,
    RiskStatus,
    Signal,
    Trade,
    TradeAction,
    TradeSide,
)
from backend.services.portfolio_service import (
    InsufficientFundsError,
    InsufficientPositionError,
    PortfolioService,
)
from backend.services.providers.market_data import MarketDataProvider

FEE_BPS = 0.5
BASE_SLIPPAGE = 0.0002
MAX_SLIPPAGE = 0.010

BUY_ACTIONS = {TradeAction.BUY, TradeAction.INCREASE, TradeAction.HEDGE}


class KillSwitchEngagedError(Exception):
    pass


class ExecutionService:
    def __init__(
        self,
        portfolio: PortfolioService,
        market: MarketDataProvider,
        repository: Repository,
        settings: Settings,
    ) -> None:
        self.portfolio = portfolio
        self.market = market
        self.repository = repository
        self.settings = settings

    # --- market ---------------------------------------------------------
    def advance_market(self, shocks: Optional[Dict[str, float]] = None) -> int:
        tick = self.market.advance_tick(shocks)
        self.repository.set_market_tick(tick)
        return tick

    # --- execution ------------------------------------------------------
    def execute(
        self,
        risk: RiskDecision,
        signal: Signal,
        decision_id: str,
        event_id: str,
    ) -> List[Trade]:
        if self.repository.get_kill_switch():
            raise KillSwitchEngagedError("Kill switch engaged - execution refused.")
        if risk.status == RiskStatus.REJECTED:
            self.repository.audit(
                "execution_service", "execution_skipped", f"decision={decision_id} risk=REJECTED"
            )
            return []
        if not self.settings.paper_trading_only:
            # Hard guarantee: Eventra never routes to a live venue.
            raise RuntimeError("Live trading is permanently disabled in Eventra.")

        impact_by_symbol = {asset.symbol: asset.impact_score for asset in signal.affected_assets}
        trades: List[Trade] = []

        for proposal in risk.approved_actions:
            trade = self._execute_one(
                proposal, signal, decision_id, event_id, impact_by_symbol.get(proposal.symbol, 50)
            )
            if trade is not None:
                trades.append(trade)

        if trades:
            self.repository.audit(
                "execution_service",
                "paper_trades_executed",
                f"decision={decision_id} count={len(trades)} symbols={[t.symbol for t in trades]}",
            )
        return trades

    def _execute_one(
        self,
        proposal: PortfolioActionProposal,
        signal: Signal,
        decision_id: str,
        event_id: str,
        impact_score: int,
    ) -> Optional[Trade]:
        symbol = proposal.symbol
        quote = self.market.quote(symbol)
        if quote is None:
            return None

        snapshot = self.portfolio.snapshot(persist=False)
        notional = self.portfolio.target_notional_for(symbol, proposal.action, proposal.percentage, snapshot)
        if notional <= 1.0:
            return None

        participation = (notional / quote.avg_daily_volume_usd) if quote.avg_daily_volume_usd else 0.0
        slippage = min(MAX_SLIPPAGE, BASE_SLIPPAGE + participation * 0.35)
        side = TradeSide.BUY if proposal.action in BUY_ACTIONS else TradeSide.SELL
        fill_price = quote.price * (1 + slippage) if side == TradeSide.BUY else quote.price * (1 - slippage)
        quantity = notional / fill_price

        position = snapshot.positions and next(
            (p for p in snapshot.positions if p.symbol == symbol), None
        )
        if side == TradeSide.SELL and position is not None:
            quantity = min(quantity, position.quantity)
        quantity = _round_quantity(symbol, quantity)
        if quantity <= 0:
            return None

        fee = (quantity * fill_price) * (FEE_BPS / 10_000.0)
        conviction = round(min(0.99, (signal.confidence * 0.7) + (impact_score / 100.0) * 0.3), 4)
        reason = (
            f"{proposal.action.value} {symbol} by {proposal.percentage:.1f}% - "
            f"{signal.recommended_action.value} on a {signal.sentiment.value} / "
            f"{signal.market_regime.value.replace('_', '-')} read ({signal.confidence:.0%} confidence)."
        )

        try:
            return self.portfolio.execute(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=round(fill_price, 4),
                action=proposal.action,
                reason=reason,
                decision_id=decision_id,
                event_id=event_id,
                fee=fee,
                slippage=slippage,
                conviction=conviction,
                signal_id=signal.id,
            )
        except (InsufficientFundsError, InsufficientPositionError, ValueError):
            self.repository.audit(
                "execution_service",
                "order_rejected_at_venue",
                f"{symbol} {proposal.action.value} could not be filled within paper constraints",
            )
            return None

    # --- reporting ------------------------------------------------------
    def trade_blotters(self, limit: int = 100) -> List[Dict[str, Any]]:
        trades: List[Trade] = self.repository.list_trades(limit=limit)
        return [trade.model_dump(mode="json") for trade in trades]


def _round_quantity(symbol: str, quantity: float) -> float:
    if symbol in {"BTC", "ETH"}:
        return round(quantity, 6)
    return round(quantity, 4)
