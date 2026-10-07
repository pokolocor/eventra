"""Deterministic risk engine.

This is the only component allowed to authorise a portfolio change. Qwen output
is treated as an untrusted *proposal*: it is re-sized, capped or discarded here
based on hard numeric limits. Nothing in this module calls an LLM.

Every check produces PASS / WARN / FAIL and a human-readable reason, so the
dashboard can show exactly why a trade was approved, reduced or rejected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.config import Settings
from backend.database.repository import Repository
from backend.models.domain import (
    CheckResult,
    PortfolioActionProposal,
    PortfolioSnapshot,
    RiskDecision,
    RiskStatus,
    Signal,
    TradeAction,
)
from backend.services.portfolio_service import PortfolioService
from backend.services.providers.market_data import MarketDataProvider

LONG_ACTIONS = {TradeAction.BUY, TradeAction.INCREASE, TradeAction.HEDGE}
EXIT_ACTIONS = {TradeAction.SELL, TradeAction.REDUCE}

CHECK_NAMES = [
    "kill_switch",
    "confidence_threshold",
    "daily_loss_limit",
    "duplicate_signal",
    "liquidity",
    "volatility",
    "position_limit",
    "portfolio_exposure",
    "max_trade_size",
    "portfolio_rules",
]


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def direction_of(action: TradeAction) -> str:
    return "long" if action in LONG_ACTIONS else "short"


class RiskEngine:
    def __init__(
        self,
        settings: Settings,
        portfolio: PortfolioService,
        market: MarketDataProvider,
        repository: Repository,
    ) -> None:
        self.settings = settings
        self.limits = settings.risk_limits
        self.portfolio = portfolio
        self.market = market
        self.repository = repository

    # --- public API -----------------------------------------------------
    def evaluate(self, signal: Signal) -> RiskDecision:
        checks: Dict[str, CheckResult] = {name: CheckResult.PASS for name in CHECK_NAMES}
        reasons: List[str] = []

        kill_switch = self.repository.get_kill_switch()
        if kill_switch:
            checks["kill_switch"] = CheckResult.FAIL
            reasons.append("Emergency kill switch is engaged - all trading halted.")
            return self._decision(
                RiskStatus.REJECTED, checks, reasons, [], 0.0, kill_switch=True
            )

        if signal.confidence < self.limits.min_confidence:
            checks["confidence_threshold"] = CheckResult.FAIL
            reasons.append(
                f"Confidence {signal.confidence:.0%} is below the "
                f"{self.limits.min_confidence:.0%} minimum required to trade."
            )
            return self._decision(RiskStatus.REJECTED, checks, reasons, [], 0.0)

        snapshot = self.portfolio.snapshot(persist=False)

        day_pnl_pct = snapshot.day_pnl_pct
        if day_pnl_pct <= -abs(self.limits.max_daily_loss_pct):
            checks["daily_loss_limit"] = CheckResult.FAIL
            reasons.append(
                f"Daily loss limit breached ({day_pnl_pct:.2f}% vs "
                f"-{self.limits.max_daily_loss_pct:.2f}%). Trading paused for the session."
            )
            return self._decision(RiskStatus.REJECTED, checks, reasons, [], 0.0)

        proposals = signal.proposed_actions[: self.limits.max_actions_per_decision]
        if len(signal.proposed_actions) > len(proposals):
            checks["portfolio_rules"] = CheckResult.WARN
            reasons.append(
                f"Capped at {self.limits.max_actions_per_decision} actions per decision "
                f"({len(signal.proposed_actions)} proposed)."
            )
        if not proposals:
            checks["portfolio_rules"] = CheckResult.WARN
            reasons.append("Qwen proposed no actionable portfolio change; nothing to execute.")
            return self._decision(RiskStatus.APPROVED, checks, reasons, [], 1.0)

        duplicates = self._duplicates(signal)
        approved: List[PortfolioActionProposal] = []
        scales: List[float] = []

        for proposal in proposals:
            outcome = self._evaluate_action(proposal, signal, snapshot, duplicates, checks, reasons)
            if outcome is None:
                continue
            adjusted, scale = outcome
            approved.append(adjusted)
            scales.append(scale)

        approved, exposure_scale = self._apply_exposure_cap(approved, snapshot, checks, reasons)
        approved, cash_scale = self._apply_cash_cap(approved, snapshot, checks, reasons)
        scales.extend([exposure_scale, cash_scale])

        if duplicates:
            checks["duplicate_signal"] = CheckResult.WARN
        if not approved:
            if checks["duplicate_signal"] == CheckResult.WARN and all(
                self._is_duplicate(p, duplicates) for p in proposals
            ):
                checks["duplicate_signal"] = CheckResult.FAIL
                reasons.append("Every proposed action duplicates a signal already acted on in the cooldown window.")
            status = RiskStatus.REJECTED
        else:
            effective_scale = min([s for s in scales if s > 0] or [1.0])
            any_failure = any(result == CheckResult.FAIL for result in checks.values())
            trimmed = (
                effective_scale < 0.999
                or len(approved) < len(proposals)
                or any_failure
            )
            status = RiskStatus.REDUCED if trimmed else RiskStatus.APPROVED

        return self._decision(
            status,
            checks,
            reasons,
            approved,
            min([s for s in scales if s > 0] or [1.0]),
        )

    # --- internals ------------------------------------------------------
    def _decision(
        self,
        status: RiskStatus,
        checks: Dict[str, CheckResult],
        reasons: List[str],
        approved: List[PortfolioActionProposal],
        scale_factor: float,
        kill_switch: bool = False,
    ) -> RiskDecision:
        ordered = list(reasons)
        if status == RiskStatus.REJECTED:
            failed = [name for name, result in checks.items() if result == CheckResult.FAIL]
            if failed:
                ordered.insert(0, f"Blocked by {', '.join(failed)}.")
        return RiskDecision(
            status=status,
            checks=checks,
            reasons=_dedupe(ordered),
            approved_actions=approved,
            scale_factor=round(max(0.0, min(1.0, scale_factor)), 4),
            limits=self.limits.as_dict(),
            kill_switch_engaged=kill_switch,
        )

    def _evaluate_action(
        self,
        proposal: PortfolioActionProposal,
        signal: Signal,
        snapshot: PortfolioSnapshot,
        duplicates: List[str],
        checks: Dict[str, CheckResult],
        reasons: List[str],
    ) -> Optional[Tuple[PortfolioActionProposal, float]]:
        symbol = proposal.symbol
        quote = self.market.quote(symbol)
        if quote is None:
            checks["portfolio_rules"] = CheckResult.FAIL
            reasons.append(f"{symbol} is not in the tradable universe; action dropped.")
            return None

        if proposal.action == TradeAction.HOLD:
            return None

        if self._is_duplicate(proposal, duplicates):
            reasons.append(
                f"{symbol} {proposal.action.value} duplicates a signal executed within the last "
                f"{self.limits.duplicate_signal_cooldown_minutes} minutes; action dropped."
            )
            checks["duplicate_signal"] = CheckResult.WARN
            return None

        # --- liquidity -------------------------------------------------
        if quote.avg_daily_volume_usd < self.limits.min_adv_usd:
            checks["liquidity"] = CheckResult.FAIL
            reasons.append(
                f"{symbol} average daily dollar volume ${quote.avg_daily_volume_usd:,.0f} is below the "
                f"${self.limits.min_adv_usd:,.0f} liquidity floor; action dropped."
            )
            return None

        # --- volatility ------------------------------------------------
        if quote.annualized_vol > self.limits.max_annualized_vol:
            checks["volatility"] = CheckResult.FAIL
            reasons.append(
                f"{symbol} annualised volatility {quote.annualized_vol:.0%} exceeds the "
                f"{self.limits.max_annualized_vol:.0%} cap; action dropped."
            )
            return None
        if quote.annualized_vol > self.limits.max_annualized_vol * 0.75:
            checks["volatility"] = CheckResult.WARN
            reasons.append(f"{symbol} volatility {quote.annualized_vol:.0%} is elevated; sizing trimmed.")

        current_weight = self._weight(symbol, snapshot)
        if proposal.action in EXIT_ACTIONS and current_weight <= 0:
            checks["portfolio_rules"] = CheckResult.FAIL
            reasons.append(
                f"{symbol} is not held, so a {proposal.action.value} is impossible; action dropped."
            )
            return None

        target_notional = self.portfolio.target_notional_for(
            symbol, proposal.action, proposal.percentage, snapshot
        )
        if target_notional <= 0:
            checks["portfolio_rules"] = CheckResult.WARN
            reasons.append(
                f"{symbol} {proposal.action.value} has no size to trade "
                f"(no existing position or zero percentage); action dropped."
            )
            return None

        allowed = target_notional
        notes: List[str] = []

        # --- participation / liquidity cap ------------------------------
        adv_cap = quote.avg_daily_volume_usd * (self.limits.max_trade_adv_pct / 100.0)
        if allowed > adv_cap:
            notes.append(
                f"{symbol} sized down to {self.limits.max_trade_adv_pct:.1f}% of ADV "
                f"(${adv_cap:,.0f} participation cap)."
            )
            allowed = adv_cap
            checks["liquidity"] = CheckResult.WARN

        # --- position limit ---------------------------------------------
        if proposal.action in LONG_ACTIONS:
            headroom = self.limits.max_position_weight_pct - current_weight
            if headroom <= 0.05:
                checks["position_limit"] = CheckResult.FAIL
                reasons.append(
                    f"{symbol} already at {current_weight:.1f}% of the portfolio "
                    f"(limit {self.limits.max_position_weight_pct:.0f}%); add rejected."
                )
                return None
            weight_cap = snapshot.portfolio_value * (headroom / 100.0)
            if allowed > weight_cap:
                notes.append(
                    f"{symbol} add capped at the {self.limits.max_position_weight_pct:.0f}% single-position "
                    f"limit (was {current_weight:.1f}%)."
                )
                allowed = weight_cap
                checks["position_limit"] = CheckResult.WARN

        # --- max trade size ---------------------------------------------
        size_cap = min(
            self.limits.max_trade_notional,
            snapshot.portfolio_value * (self.limits.max_single_trade_pct / 100.0),
        )
        if allowed > size_cap:
            notes.append(
                f"{symbol} notional trimmed to ${size_cap:,.0f} "
                f"(max {self.limits.max_single_trade_pct:.0f}% of portfolio / "
                f"${self.limits.max_trade_notional:,.0f} per trade)."
            )
            allowed = size_cap
            checks["max_trade_size"] = CheckResult.WARN

        if allowed <= 0:
            checks["portfolio_rules"] = CheckResult.FAIL
            reasons.append(f"{symbol} sized to zero after risk limits; action dropped.")
            return None

        scale = allowed / target_notional if target_notional else 1.0
        adjusted_percentage = round(min(100.0, proposal.percentage * scale), 4)
        if adjusted_percentage <= 0:
            return None

        reasons.extend(notes)
        return PortfolioActionProposal(
            symbol=symbol, action=proposal.action, percentage=adjusted_percentage
        ), scale

    def _weight(self, symbol: str, snapshot: PortfolioSnapshot) -> float:
        if not snapshot.portfolio_value:
            return 0.0
        position = next((p for p in snapshot.positions if p.symbol == symbol.upper()), None)
        return (position.market_value / snapshot.portfolio_value * 100.0) if position else 0.0

    def _notional_of(
        self, proposal: PortfolioActionProposal, snapshot: PortfolioSnapshot
    ) -> float:
        return self.portfolio.target_notional_for(
            proposal.symbol, proposal.action, proposal.percentage, snapshot
        )

    def _percentage_for(
        self,
        proposal: PortfolioActionProposal,
        notional: float,
        snapshot: PortfolioSnapshot,
    ) -> float:
        full = self._notional_of(
            PortfolioActionProposal(symbol=proposal.symbol, action=proposal.action, percentage=100.0),
            snapshot,
        )
        if full <= 0:
            return 0.0
        return round(max(0.0, min(100.0, (notional / full) * 100.0)), 4)

    def _apply_exposure_cap(
        self,
        proposals: List[PortfolioActionProposal],
        snapshot: PortfolioSnapshot,
        checks: Dict[str, CheckResult],
        reasons: List[str],
    ) -> Tuple[List[PortfolioActionProposal], float]:
        if not proposals or not snapshot.portfolio_value:
            return proposals, 1.0

        notionals = {index: self._notional_of(p, snapshot) for index, p in enumerate(proposals)}
        exits = sum(v for i, v in notionals.items() if proposals[i].action in EXIT_ACTIONS)
        adds = sum(v for i, v in notionals.items() if proposals[i].action in LONG_ACTIONS)
        projected = snapshot.positions_value - exits + adds
        projected_exposure = projected / snapshot.portfolio_value * 100.0

        if projected_exposure <= self.limits.max_gross_exposure_pct or adds <= 0:
            if projected_exposure > self.limits.max_gross_exposure_pct:
                checks["portfolio_exposure"] = CheckResult.WARN
                reasons.append(
                    f"Projected gross exposure {projected_exposure:.1f}% exceeds "
                    f"{self.limits.max_gross_exposure_pct:.0f}% but no adds are available to trim."
                )
            return proposals, 1.0

        max_adds = max(0.0, snapshot.portfolio_value * (self.limits.max_gross_exposure_pct / 100.0)
                       - (snapshot.positions_value - exits))
        scale = max(0.0, min(1.0, max_adds / adds)) if adds else 1.0
        checks["portfolio_exposure"] = CheckResult.WARN
        reasons.append(
            f"Gross exposure would reach {projected_exposure:.1f}% (limit "
            f"{self.limits.max_gross_exposure_pct:.0f}%); new buys scaled to {scale:.0%}."
        )

        adjusted: List[PortfolioActionProposal] = []
        for index, proposal in enumerate(proposals):
            if proposal.action in LONG_ACTIONS:
                new_notional = notionals[index] * scale
                percentage = self._percentage_for(proposal, new_notional, snapshot)
                if percentage <= 0:
                    continue
                adjusted.append(
                    PortfolioActionProposal(symbol=proposal.symbol, action=proposal.action, percentage=percentage)
                )
            else:
                adjusted.append(proposal)
        return adjusted, scale

    def _apply_cash_cap(
        self,
        proposals: List[PortfolioActionProposal],
        snapshot: PortfolioSnapshot,
        checks: Dict[str, CheckResult],
        reasons: List[str],
    ) -> Tuple[List[PortfolioActionProposal], float]:
        if not proposals:
            return proposals, 1.0

        notionals = {index: self._notional_of(p, snapshot) for index, p in enumerate(proposals)}
        buys = [(i, v) for i, v in notionals.items() if proposals[i].action in LONG_ACTIONS]
        sells = sum(v for i, v in notionals.items() if proposals[i].action in EXIT_ACTIONS)
        total_buys = sum(v for _, v in buys)
        available = max(0.0, snapshot.cash + sells * 0.98)
        if total_buys <= 0 or total_buys <= available:
            return proposals, 1.0

        scale = available / total_buys
        checks["portfolio_rules"] = CheckResult.WARN
        reasons.append(
            f"Available cash ${available:,.0f} covers only {scale:.0%} of the requested buys; "
            "sizes trimmed to stay fully funded (no margin in paper mode)."
        )

        adjusted: List[PortfolioActionProposal] = []
        for index, proposal in enumerate(proposals):
            if proposal.action in LONG_ACTIONS:
                percentage = self._percentage_for(proposal, notionals[index] * scale, snapshot)
                if percentage <= 0:
                    continue
                adjusted.append(
                    PortfolioActionProposal(symbol=proposal.symbol, action=proposal.action, percentage=percentage)
                )
            else:
                adjusted.append(proposal)
        return adjusted, scale

    # --- duplicate detection --------------------------------------------
    def _duplicates(self, signal: Signal) -> List[str]:
        cooldown = timedelta(minutes=self.limits.duplicate_signal_cooldown_minutes)
        cutoff = datetime.now(timezone.utc) - cooldown
        keys: List[str] = []
        for record in self.repository.list_signals(limit=300):
            created = _parse_timestamp(record.get("created_at"))
            if created is None or created < cutoff:
                continue
            keys.append(f"{str(record.get('symbol', '')).upper()}:{record.get('direction', '')}")
        return keys

    @staticmethod
    def _is_duplicate(proposal: PortfolioActionProposal, duplicates: List[str]) -> bool:
        return f"{proposal.symbol.upper()}:{direction_of(proposal.action)}" in duplicates

    def record_executed_signal(self, signal: Signal, decision_id: str) -> None:
        now = datetime.now(timezone.utc)
        for proposal in signal.proposed_actions:
            self.repository.record_signal(
                {
                    "created_at": now.isoformat(),
                    "symbol": proposal.symbol,
                    "direction": direction_of(proposal.action),
                    "action": proposal.action.value,
                    "decision_id": decision_id,
                    "event_id": signal.event_id,
                    "confidence": signal.confidence,
                }
            )


def _dedupe(items: List[str]) -> List[str]:
    seen: Dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen.keys())
