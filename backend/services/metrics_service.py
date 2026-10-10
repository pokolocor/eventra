"""Performance metrics service.

Computes Sharpe ratio, max drawdown, win rate, and other key metrics
from the paper-trading history for hackathon submission requirements.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.database.repository import Repository
from backend.models.domain import DecisionRun, EquityPoint, Trade


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetricsService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def compute_all(self) -> Dict[str, Any]:
        """Compute all performance metrics from historical data."""
        trades = self.repository.list_trades(limit=1000)
        equity = self.repository.list_equity(limit=2000)
        decisions = self.repository.list_decisions(limit=200)

        return {
            "sharpe_ratio": self._sharpe_ratio(equity),
            "sortino_ratio": self._sortino_ratio(equity),
            "max_drawdown": self._max_drawdown(equity),
            "max_drawdown_pct": self._max_drawdown_pct(equity),
            "win_rate": self._win_rate(trades),
            "profit_factor": self._profit_factor(trades),
            "total_trades": len(trades),
            "winning_trades": len([t for t in trades if t.realized_pnl > 0]),
            "losing_trades": len([t for t in trades if t.realized_pnl < 0]),
            "total_realized_pnl": sum(t.realized_pnl for t in trades),
            "avg_win": self._avg_win(trades),
            "avg_loss": self._avg_loss(trades),
            "largest_win": self._largest_win(trades),
            "largest_loss": self._largest_loss(trades),
            "total_fees": sum(t.fee for t in trades),
            "total_slippage": sum(t.slippage * t.notional for t in trades),
            "risk_violations": self._count_risk_violations(decisions),
            "decisions_total": len(decisions),
            "decisions_executed": len([d for d in decisions if d.trades]),
            "decisions_rejected": len(
                [d for d in decisions if d.risk and d.risk.status.value == "REJECTED"]
            ),
            "paper_trading_days": self._trading_days(trades),
            "last_updated": utcnow().isoformat(),
        }

    def _sharpe_ratio(
        self, equity: List[EquityPoint], risk_free_rate: float = 0.0
    ) -> float:
        """Annualized Sharpe ratio from equity curve."""
        if len(equity) < 2:
            return 0.0

        returns = []
        for i in range(1, len(equity)):
            prev_value = equity[i - 1].portfolio_value
            curr_value = equity[i].portfolio_value
            if prev_value > 0:
                ret = (curr_value - prev_value) / prev_value
                returns.append(ret)

        if len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0

        if std_dev == 0:
            return 0.0

        # Annualize assuming ~252 trading days
        annualized_return = mean_return * 252
        annualized_std = std_dev * math.sqrt(252)

        return (
            round((annualized_return - risk_free_rate) / annualized_std, 4)
            if annualized_std > 0
            else 0.0
        )

    def _sortino_ratio(
        self, equity: List[EquityPoint], risk_free_rate: float = 0.0
    ) -> float:
        """Annualized Sortino ratio (only downside deviation)."""
        if len(equity) < 2:
            return 0.0

        returns = []
        for i in range(1, len(equity)):
            prev_value = equity[i - 1].portfolio_value
            curr_value = equity[i].portfolio_value
            if prev_value > 0:
                ret = (curr_value - prev_value) / prev_value
                returns.append(ret)

        if len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        downside_returns = [r for r in returns if r < 0]

        if not downside_returns:
            return 0.0

        downside_variance = sum(r**2 for r in downside_returns) / len(downside_returns)
        downside_dev = math.sqrt(downside_variance)

        if downside_dev == 0:
            return 0.0

        annualized_return = mean_return * 252
        annualized_downside = downside_dev * math.sqrt(252)

        return (
            round((annualized_return - risk_free_rate) / annualized_downside, 4)
            if annualized_downside > 0
            else 0.0
        )

    def _max_drawdown(self, equity: List[EquityPoint]) -> float:
        """Maximum drawdown in absolute dollars."""
        if not equity:
            return 0.0

        peak = equity[0].portfolio_value
        max_dd = 0.0

        for point in equity:
            if point.portfolio_value > peak:
                peak = point.portfolio_value
            dd = peak - point.portfolio_value
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)

    def _max_drawdown_pct(self, equity: List[EquityPoint]) -> float:
        """Maximum drawdown as percentage."""
        if not equity:
            return 0.0

        peak = equity[0].portfolio_value
        max_dd_pct = 0.0

        for point in equity:
            if point.portfolio_value > peak:
                peak = point.portfolio_value
            if peak > 0:
                dd_pct = (peak - point.portfolio_value) / peak * 100.0
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        return round(max_dd_pct, 4)

    def _win_rate(self, trades: List[Trade]) -> float:
        """Percentage of winning trades."""
        if not trades:
            return 0.0

        winners = len([t for t in trades if t.realized_pnl > 0])
        return round((winners / len(trades)) * 100.0, 2)

    def _profit_factor(self, trades: List[Trade]) -> float:
        """Gross profit / gross loss ratio."""
        gross_profit = sum(t.realized_pnl for t in trades if t.realized_pnl > 0)
        gross_loss = abs(sum(t.realized_pnl for t in trades if t.realized_pnl < 0))

        if gross_loss == 0:
            return 0.0 if gross_profit == 0 else float("inf")

        return round(gross_profit / gross_loss, 4)

    def _avg_win(self, trades: List[Trade]) -> float:
        """Average winning trade PnL."""
        wins = [t.realized_pnl for t in trades if t.realized_pnl > 0]
        return round(sum(wins) / len(wins), 2) if wins else 0.0

    def _avg_loss(self, trades: List[Trade]) -> float:
        """Average losing trade PnL."""
        losses = [t.realized_pnl for t in trades if t.realized_pnl < 0]
        return round(sum(losses) / len(losses), 2) if losses else 0.0

    def _largest_win(self, trades: List[Trade]) -> float:
        """Largest single winning trade."""
        wins = [t.realized_pnl for t in trades if t.realized_pnl > 0]
        return round(max(wins), 2) if wins else 0.0

    def _largest_loss(self, trades: List[Trade]) -> float:
        """Largest single losing trade."""
        losses = [t.realized_pnl for t in trades if t.realized_pnl < 0]
        return round(min(losses), 2) if losses else 0.0

    def _count_risk_violations(self, decisions: List[DecisionRun]) -> int:
        """Count decisions where risk engine rejected or reduced position."""
        violations = 0
        for d in decisions:
            if d.risk:
                if d.risk.status.value in ("REJECTED", "REDUCED"):
                    violations += 1
        return violations

    def _trading_days(self, trades: List[Trade]) -> int:
        """Number of unique trading days in the trade history."""
        if not trades:
            return 0

        days = set()
        for t in trades:
            days.add(t.created_at.date())

        return len(days)
