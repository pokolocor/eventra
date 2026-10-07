"""Repository interface + implementations.

`JsonFileRepository` is the zero-dependency default (works with no database
installed). `SqlRepository` persists the same entities through SQLAlchemy to
PostgreSQL or SQLite. Both satisfy `Repository`, so the services layer never
knows which one is active.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import Settings
from backend.models.domain import DecisionRun, EquityPoint, Event, Position, Trade

class Repository(ABC):
    # --- events ---------------------------------------------------------
    @abstractmethod
    def save_event(self, event: Event) -> None: ...

    @abstractmethod
    def list_events(self, limit: int = 50) -> List[Event]: ...

    @abstractmethod
    def get_event(self, event_id: str) -> Optional[Event]: ...

    # --- decisions ------------------------------------------------------
    @abstractmethod
    def save_decision(self, run: DecisionRun) -> None: ...

    @abstractmethod
    def list_decisions(self, limit: int = 25) -> List[DecisionRun]: ...

    @abstractmethod
    def get_decision(self, decision_id: str) -> Optional[DecisionRun]: ...

    # --- trades ---------------------------------------------------------
    @abstractmethod
    def save_trade(self, trade: Trade) -> None: ...

    @abstractmethod
    def list_trades(self, limit: int = 100) -> List[Trade]: ...

    # --- portfolio ------------------------------------------------------
    @abstractmethod
    def load_portfolio(self) -> PortfolioState: ...

    @abstractmethod
    def save_portfolio(self, state: PortfolioState) -> None: ...

    @abstractmethod
    def append_equity_point(self, point: EquityPoint) -> None: ...

    @abstractmethod
    def list_equity(self, limit: int = 240) -> List[EquityPoint]: ...

    # --- system ---------------------------------------------------------
    @abstractmethod
    def load_system(self) -> SystemState: ...

    @abstractmethod
    def save_system(self, state: SystemState) -> None: ...

    @abstractmethod
    def audit(self, actor: str, action: str, detail: str = "") -> None: ...

    @abstractmethod
    def reset(self) -> None: ...

    # --- convenience ----------------------------------------------------
    def set_kill_switch(self, engaged: bool) -> None:
        state = self.load_system()
        state.kill_switch = bool(engaged)
        self.save_system(state)
        self.audit("operator", "kill_switch", "engaged" if engaged else "disengaged")

    def get_kill_switch(self) -> bool:
        return self.load_system().kill_switch

    def set_market_tick(self, tick: int) -> None:
        state = self.load_system()
        state.market_tick = int(tick)
        self.save_system(state)

    def record_signal(self, entry: Dict[str, Any]) -> None:
        state = self.load_system()
        state.signals.append(entry)
        state.signals = state.signals[-500:]
        self.save_system(state)

    def list_signals(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.load_system().signals[-limit:]

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.load_system().audit[-limit:]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JsonFileRepository(Repository):
    """Atomic JSON-file store. Default for Demo Mode and zero-install runs."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = self._read()

    # --- storage helpers ------------------------------------------------
    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            backup = self.path.with_suffix(".corrupt.json")
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            return self._empty_state()

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {
            "version": 1,
            "events": [],
            "decisions": [],
            "trades": [],
            "equity": [],
            "portfolio": {},
            "system": {},
            "seeded": False,
        }

    def _flush(self) -> None:
        with self._lock:
            handle, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(self._state, stream, indent=2, default=str)
                os.replace(tmp, self.path)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise

    def reload(self) -> None:
        with self._lock:
            self._state = self._read()

    @property
    def seeded(self) -> bool:
        return bool(self._state.get("seeded"))

    def mark_seeded(self) -> None:
        with self._lock:
            self._state["seeded"] = True
            self._flush()

    # --- events ---------------------------------------------------------
    def save_event(self, event: Event) -> None:
        with self._lock:
            events = self._state.setdefault("events", [])
            payload = event.model_dump(mode="json")
            for index, existing in enumerate(events):
                if existing.get("id") == event.id:
                    events[index] = payload
                    break
            else:
                events.append(payload)
            self._state["events"] = events[-500:]
            self._flush()

    def list_events(self, limit: int = 50) -> List[Event]:
        with self._lock:
            raw = list(self._state.get("events", []))
        raw.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return [Event.model_validate(item) for item in raw[:limit]]

    def get_event(self, event_id: str) -> Optional[Event]:
        with self._lock:
            for item in self._state.get("events", []):
                if item.get("id") == event_id:
                    return Event.model_validate(item)
        return None

    # --- decisions ------------------------------------------------------
    def save_decision(self, run: DecisionRun) -> None:
        with self._lock:
            decisions = self._state.setdefault("decisions", [])
            payload = run.model_dump(mode="json")
            for index, existing in enumerate(decisions):
                if existing.get("id") == run.id:
                    decisions[index] = payload
                    break
            else:
                decisions.append(payload)
            self._state["decisions"] = decisions[-200:]
            self._flush()

    def list_decisions(self, limit: int = 25) -> List[DecisionRun]:
        with self._lock:
            raw = list(self._state.get("decisions", []))
        raw.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        return [DecisionRun.model_validate(item) for item in raw[:limit]]

    def get_decision(self, decision_id: str) -> Optional[DecisionRun]:
        with self._lock:
            for item in self._state.get("decisions", []):
                if item.get("id") == decision_id:
                    return DecisionRun.model_validate(item)
        return None

    # --- trades ---------------------------------------------------------
    def save_trade(self, trade: Trade) -> None:
        with self._lock:
            trades = self._state.setdefault("trades", [])
            trades.append(trade.model_dump(mode="json"))
            self._state["trades"] = trades[-1000:]
            self._flush()

    def list_trades(self, limit: int = 100) -> List[Trade]:
        with self._lock:
            raw = list(self._state.get("trades", []))
        raw.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return [Trade.model_validate(item) for item in raw[:limit]]

    # --- portfolio ------------------------------------------------------
    def load_portfolio(self) -> PortfolioState:
        with self._lock:
            data = dict(self._state.get("portfolio") or {})
        if not data:
            return PortfolioState()
        return PortfolioState.from_dict(data)

    def save_portfolio(self, state: PortfolioState) -> None:
        with self._lock:
            self._state["portfolio"] = state.to_dict()
            self._flush()

    def append_equity_point(self, point: EquityPoint) -> None:
        with self._lock:
            equity = self._state.setdefault("equity", [])
            equity.append(point.model_dump(mode="json"))
            self._state["equity"] = equity[-2000:]
            self._flush()

    def list_equity(self, limit: int = 240) -> List[EquityPoint]:
        with self._lock:
            raw = list(self._state.get("equity", []))
        raw.sort(key=lambda p: p.get("timestamp", ""))
        return [EquityPoint.model_validate(item) for item in raw[-limit:]]

    # --- system ---------------------------------------------------------
    def load_system(self) -> SystemState:
        with self._lock:
            data = dict(self._state.get("system") or {})
        return SystemState.from_dict(data)

    def save_system(self, state: SystemState) -> None:
        with self._lock:
            self._state["system"] = state.to_dict()
            self._flush()

    def audit(self, actor: str, action: str, detail: str = "") -> None:
        with self._lock:
            system = self.load_system()
            system.audit.append(
                {"timestamp": _now().isoformat(), "actor": actor, "action": action, "detail": detail}
            )
            system.audit = system.audit[-1000:]
            self.save_system(system)

    def reset(self) -> None:
        with self._lock:
            self._state = self._empty_state()
            self._flush()


class SqlRepository(Repository):
    """SQLAlchemy-backed repository (PostgreSQL in production, SQLite locally)."""

    def __init__(self, settings: Settings) -> None:
        from backend.database.session import create_session_factory, try_init_schema

        self.settings = settings
        try_init_schema(settings)
        self._session_factory = create_session_factory(settings)
        self._lock = threading.RLock()

    def _session(self) -> Any:
        return self._session_factory()

    # --- events ---------------------------------------------------------
    def save_event(self, event: Event) -> None:
        from backend.database.orm import EventRow

        payload = event.model_dump(mode="json")
        with self._lock, self._session() as session:
            row = session.get(EventRow, event.id)
            if row is None:
                row = EventRow(id=event.id)
                session.add(row)
            row.timestamp = event.timestamp
            row.title = event.title
            row.source = event.source
            row.category = event.category.value
            row.importance = event.importance.value
            row.summary = event.summary
            row.affected_assets = list(event.affected_assets)
            row.raw = dict(event.raw)
            row.template_key = event.template_key
            row.is_simulated = event.is_simulated
            row.payload = payload
            session.commit()

    def list_events(self, limit: int = 50) -> List[Event]:
        from backend.database.orm import EventRow

        with self._session() as session:
            rows = (
                session.query(EventRow).order_by(EventRow.timestamp.desc()).limit(limit).all()
            )
            return [Event.model_validate(row.payload) for row in rows]

    def get_event(self, event_id: str) -> Optional[Event]:
        from backend.database.orm import EventRow

        with self._session() as session:
            row = session.get(EventRow, event_id)
            return Event.model_validate(row.payload) if row else None

    # --- decisions ------------------------------------------------------
    def save_decision(self, run: DecisionRun) -> None:
        from backend.database.orm import DecisionRow

        payload = run.model_dump(mode="json")
        with self._lock, self._session() as session:
            row = session.get(DecisionRow, run.id)
            if row is None:
                row = DecisionRow(id=run.id)
                session.add(row)
            row.created_at = run.created_at
            row.event_id = run.event.id
            row.status = run.status
            row.llm_provider = run.llm_provider
            row.mode = run.mode
            row.risk_status = run.risk.status.value if run.risk else None
            row.explanation = run.explanation
            row.error = run.error
            row.payload = payload
            session.commit()

    def list_decisions(self, limit: int = 25) -> List[DecisionRun]:
        from backend.database.orm import DecisionRow

        with self._session() as session:
            rows = (
                session.query(DecisionRow).order_by(DecisionRow.created_at.desc()).limit(limit).all()
            )
            return [DecisionRun.model_validate(row.payload) for row in rows]

    def get_decision(self, decision_id: str) -> Optional[DecisionRun]:
        from backend.database.orm import DecisionRow

        with self._session() as session:
            row = session.get(DecisionRow, decision_id)
            return DecisionRun.model_validate(row.payload) if row else None

    # --- trades ---------------------------------------------------------
    def save_trade(self, trade: Trade) -> None:
        from backend.database.orm import TradeRow

        with self._lock, self._session() as session:
            if session.get(TradeRow, trade.id) is not None:
                return
            session.add(TradeRow(**trade.model_dump(mode="json")))
            session.commit()

    def list_trades(self, limit: int = 100) -> List[Trade]:
        from backend.database.orm import TradeRow

        with self._session() as session:
            rows = session.query(TradeRow).order_by(TradeRow.created_at.desc()).limit(limit).all()
            return [
                Trade.model_validate(
                    {c.name: getattr(row, c.name) for c in row.__table__.columns}
                )
                for row in rows
            ]

    # --- portfolio ------------------------------------------------------
    def load_portfolio(self) -> PortfolioState:
        from backend.database.orm import PositionRow, PortfolioStateRow

        with self._session() as session:
            head = session.get(PortfolioStateRow, 1)
            if head is None:
                return PortfolioState()
            positions = {row.symbol: row for row in session.query(PositionRow).all()}
            state = PortfolioState(
                starting_balance=head.starting_balance,
                cash=head.cash,
                realized_pnl=head.realized_pnl,
                day_start_value=head.day_start_value,
            )
            for symbol, row in positions.items():
                state.positions[symbol] = Position.model_validate(
                    {
                        "symbol": row.symbol,
                        "quantity": row.quantity,
                        "avg_entry_price": row.avg_entry_price,
                        "last_price": row.last_price,
                        "conviction": row.conviction,
                        "last_signal_id": row.last_signal_id,
                        "opened_at": row.opened_at,
                        "updated_at": row.updated_at,
                    }
                )
            return state

    def save_portfolio(self, state: PortfolioState) -> None:
        from backend.database.orm import PositionRow, PortfolioStateRow

        with self._lock, self._session() as session:
            head = session.get(PortfolioStateRow, 1)
            if head is None:
                head = PortfolioStateRow(id=1)
                session.add(head)
            head.starting_balance = state.starting_balance
            head.cash = state.cash
            head.realized_pnl = state.realized_pnl
            head.day_start_value = state.day_start_value
            head.updated_at = _now()

            existing = {row.symbol: row for row in session.query(PositionRow).all()}
            for symbol in set(existing) - set(state.positions):
                session.delete(existing[symbol])
            for symbol, position in state.positions.items():
                row = existing.get(symbol)
                if row is None:
                    row = PositionRow(symbol=symbol)
                    session.add(row)
                row.quantity = position.quantity
                row.avg_entry_price = position.avg_entry_price
                row.last_price = position.last_price
                row.conviction = position.conviction
                row.last_signal_id = position.last_signal_id
                row.opened_at = position.opened_at
                row.updated_at = position.updated_at
            session.commit()

    def append_equity_point(self, point: EquityPoint) -> None:
        from backend.database.orm import EquityPointRow

        with self._lock, self._session() as session:
            session.add(
                EquityPointRow(
                    timestamp=point.timestamp,
                    portfolio_value=point.portfolio_value,
                    cash=point.cash,
                    exposure=point.exposure,
                )
            )
            session.commit()

    def list_equity(self, limit: int = 240) -> List[EquityPoint]:
        from sqlalchemy import func
        from backend.database.orm import EquityPointRow

        with self._session() as session:
            total = session.query(func.count(EquityPointRow.id)).scalar() or 0
            offset = max(0, int(total) - limit)
            rows = (
                session.query(EquityPointRow)
                .order_by(EquityPointRow.timestamp.asc())
                .offset(offset)
                .all()
            )
            return [
                EquityPoint(
                    timestamp=row.timestamp,
                    portfolio_value=row.portfolio_value,
                    cash=row.cash,
                    exposure=row.exposure,
                )
                for row in rows
            ]

    # --- system ---------------------------------------------------------
    def load_system(self) -> SystemState:
        from backend.database.orm import PortfolioStateRow, SignalRecordRow

        with self._session() as session:
            head = session.get(PortfolioStateRow, 1)
            signals = [
                row.payload for row in session.query(SignalRecordRow)
                .order_by(SignalRecordRow.created_at.desc())
                .limit(500)
                .all()
            ]
            return SystemState(
                kill_switch=bool(head.kill_switch) if head else False,
                market_tick=int(head.market_tick) if head else 0,
                signals=list(reversed(signals)),
                audit=[],
            )

    def save_system(self, state: SystemState) -> None:
        from backend.database.orm import PortfolioStateRow

        with self._lock, self._session() as session:
            head = session.get(PortfolioStateRow, 1)
            if head is None:
                head = PortfolioStateRow(id=1)
                session.add(head)
            head.kill_switch = state.kill_switch
            head.market_tick = state.market_tick
            head.updated_at = _now()
            session.commit()

    def record_signal(self, entry: Dict[str, Any]) -> None:
        from backend.database.orm import SignalRecordRow

        timestamp = entry.get("created_at")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        with self._lock, self._session() as session:
            session.add(
                SignalRecordRow(
                    created_at=timestamp or _now(),
                    symbol=entry.get("symbol", ""),
                    direction=entry.get("direction", ""),
                    action=entry.get("action", ""),
                    decision_id=entry.get("decision_id"),
                    payload=entry,
                )
            )
            session.commit()

    def audit(self, actor: str, action: str, detail: str = "") -> None:
        from backend.database.orm import AuditLogRow

        with self._lock, self._session() as session:
            session.add(
                AuditLogRow(timestamp=_now(), actor=actor, action=action, detail=detail)
            )
            session.commit()

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        from backend.database.orm import AuditLogRow

        with self._session() as session:
            rows = (
                session.query(AuditLogRow).order_by(AuditLogRow.timestamp.desc()).limit(limit).all()
            )
            return [
                {
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "actor": row.actor,
                    "action": row.action,
                    "detail": row.detail,
                }
                for row in reversed(rows)
            ]

    def reset(self) -> None:
        from backend.database.orm import (
            AuditLogRow,
            DecisionRow,
            EquityPointRow,
            EventRow,
            PortfolioStateRow,
            PositionRow,
            SignalRecordRow,
            TradeRow,
        )

        with self._lock, self._session() as session:
            for model in (
                AuditLogRow,
                SignalRecordRow,
                EquityPointRow,
                TradeRow,
                DecisionRow,
                EventRow,
                PositionRow,
                PortfolioStateRow,
            ):
                session.query(model).delete()
            session.commit()


def create_repository(settings: Settings, force: Optional[str] = None) -> Repository:
    """Pick a repository backend from configuration.

    `EVENTRA_STORE=sql|json` overrides auto-detection. Auto-detection uses SQL
    whenever SQLAlchemy is importable, otherwise the JSON file store.
    """

    from backend.database.session import sqlalchemy_available

    choice = (force or os.environ.get("EVENTRA_STORE", "")).strip().lower()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / "eventra_state.json"

    if choice == "json":
        return JsonFileRepository(json_path)
    if choice == "sql":
        return SqlRepository(settings)
    if sqlalchemy_available():
        try:
            return SqlRepository(settings)
        except Exception:
            return JsonFileRepository(json_path)
    return JsonFileRepository(json_path)
