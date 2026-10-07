"""Serialisable portfolio/system state used by both repository backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.models.domain import Position


@dataclass
class PortfolioState:
    starting_balance: float = 1_000_000.0
    cash: float = 0.0
    realized_pnl: float = 0.0
    day_start_value: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "starting_balance": self.starting_balance,
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
            "day_start_value": self.day_start_value,
            "positions": {
                symbol: position.model_dump(mode="json") for symbol, position in self.positions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioState":
        raw_positions = data.get("positions") or {}
        positions: Dict[str, Position] = {}
        for symbol, payload in raw_positions.items():
            positions[symbol] = Position.model_validate(payload)
        return cls(
            starting_balance=float(data.get("starting_balance", 1_000_000.0)),
            cash=float(data.get("cash", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            day_start_value=float(data.get("day_start_value", 0.0)),
            positions=positions,
        )


@dataclass
class SystemState:
    kill_switch: bool = False
    market_tick: int = 0
    signals: List[Dict[str, Any]] = field(default_factory=list)
    audit: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kill_switch": self.kill_switch,
            "market_tick": self.market_tick,
            "signals": self.signals,
            "audit": self.audit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemState":
        return cls(
            kill_switch=bool(data.get("kill_switch", False)),
            market_tick=int(data.get("market_tick", 0)),
            signals=list(data.get("signals") or []),
            audit=list(data.get("audit") or []),
        )
