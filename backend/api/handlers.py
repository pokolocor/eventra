"""Transport-agnostic API handlers.

The FastAPI routers and the zero-dependency dev server both call these
functions, which guarantees the two servers expose exactly the same JSON
contract.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.models.domain import DecisionRun, Event
from backend.observability import get_logger
from backend.security import Principal, anonymous, require_reset_allowed
from backend.services.registry import ServiceRegistry

logger = get_logger("api")


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def decision_to_dict(run: DecisionRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "status": run.status,
        "mode": run.mode,
        "llm_provider": run.llm_provider,
        "error": run.error,
        "explanation": run.explanation,
        "event": _jsonable(run.event),
        "analysis": _jsonable(run.analysis),
        "signal": _jsonable(run.signal),
        "risk": run.risk.to_public_dict() if run.risk else None,
        "trades": [_jsonable(t) for t in run.trades],
        "timeline": [_jsonable(entry) for entry in run.timeline],
        "portfolio_after": _jsonable(run.portfolio_after),
        "summary": summarise(run),
    }


def summarise(run: DecisionRun) -> Dict[str, Any]:
    risk_status = run.risk.status.value if run.risk else None
    return {
        "stage": run.status,
        "risk_status": risk_status,
        "confidence": run.analysis.confidence if run.analysis else None,
        "sentiment": run.analysis.sentiment.value if run.analysis else None,
        "market_regime": run.analysis.market_regime.value if run.analysis else None,
        "recommended_action": run.analysis.recommended_action.value
        if run.analysis
        else None,
        "trade_count": len(run.trades),
        "symbols": sorted({t.symbol for t in run.trades}),
        "stages_completed": [entry.stage.value for entry in run.timeline],
    }


# --- system -------------------------------------------------------------
def system_status(registry: ServiceRegistry) -> Dict[str, Any]:
    status = registry.settings.public_status()
    state = registry.repository.load_system()
    decisions = registry.repository.list_decisions(limit=200)
    executed = [d for d in decisions if d.trades]
    status.update(
        {
            "kill_switch": state.kill_switch,
            "market_tick": state.market_tick,
            "counts": {
                "events": len(registry.repository.list_events(limit=500)),
                "decisions": len(decisions),
                "trades": len(registry.repository.list_trades(limit=1000)),
                "positions": len(registry.portfolio.state().positions),
            },
            "agent": {
                "decisions_total": len(decisions),
                "decisions_executed": len(executed),
                "decisions_rejected": len(
                    [
                        d
                        for d in decisions
                        if d.risk and d.risk.status.value == "REJECTED"
                    ]
                ),
                "last_decision_id": decisions[0].id if decisions else None,
            },
        }
    )
    # Reflect the store actually in use, not just what configuration asked for.
    status.setdefault("database", {})
    status["database"]["backend"] = registry.repository.kind
    status["database"]["persistent"] = registry.repository.persistent
    return status


def readiness(registry: ServiceRegistry) -> Dict[str, Any]:
    """Readiness probe: can this process serve traffic right now?

    Deliberately does *not* require a configured LLM - `demo-mock` is a
    supported production path for the demo - but it does require the store.
    """

    checks: Dict[str, Any] = {}

    try:
        registry.repository.load_system()
        checks["store"] = {
            "status": "ok",
            "kind": registry.repository.kind,
            "persistent": registry.repository.persistent,
        }
        store_ready = True
    except Exception as exc:  # pragma: no cover - depends on the live database
        checks["store"] = {"status": "error", "error_type": type(exc).__name__}
        store_ready = False

    settings = registry.settings
    checks["llm"] = {
        "status": "ok",
        "provider": "qwen" if settings.qwen_available else "demo-mock",
        "configured": settings.qwen_available,
        "model": settings.qwen_model,
    }

    ready = store_ready
    return {
        "status": "ready" if ready else "unavailable",
        "ready": ready,
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "mode": "PAPER / DEMO" if settings.demo_mode else "PAPER",
        "paper_trading_only": settings.paper_trading_only,
        "kill_switch": registry.repository.get_kill_switch(),
        "checks": checks,
    }


def _log_control(
    principal: Optional[Principal],
    action: str,
    detail: str = "",
    outcome: str = "ok",
) -> None:
    """Structured log line for a control-plane action."""

    who = principal or anonymous()
    logger.info(
        "control action",
        extra={
            "request_id": who.request_id,
            "extra_fields": {
                "action": action,
                "actor": who.actor,
                "ip": who.ip,
                "outcome": outcome,
                "detail": detail[:200],
            },
        },
    )


def _audit_control(
    registry: ServiceRegistry,
    principal: Optional[Principal],
    action: str,
    detail: str = "",
    outcome: str = "ok",
) -> None:
    """Persist a control-plane action (actor + IP + timestamp) and log it."""

    who = principal or anonymous()
    registry.repository.audit(who.actor, action, detail, ip=who.ip)
    _log_control(who, action, detail, outcome)


def set_kill_switch(
    registry: ServiceRegistry, engaged: bool, principal: Optional[Principal] = None
) -> Dict[str, Any]:
    who = principal or anonymous()
    registry.guard.check_control(who.ip, "kill-switch")
    registry.repository.set_kill_switch(bool(engaged), actor=who.actor, ip=who.ip)
    engaged_now = registry.repository.get_kill_switch()
    # `set_kill_switch` already persisted the audit row (with actor + IP).
    _log_control(who, "kill_switch", "engaged" if engaged_now else "disengaged")
    return {"kill_switch": engaged_now}


def reset_demo(
    registry: ServiceRegistry, principal: Optional[Principal] = None
) -> Dict[str, Any]:
    who = principal or anonymous()
    require_reset_allowed(registry.settings)
    registry.guard.check_control(who.ip, "reset")
    result = registry.reset()
    registry.guard.reset()
    _audit_control(registry, who, "system_reset", f"seeded={result.get('seeded')}")
    return {"ok": True, **result}


def audit_log(registry: ServiceRegistry, limit: int = 100) -> List[Dict[str, Any]]:
    return list(reversed(registry.repository.list_audit(limit=limit)))


# --- events -------------------------------------------------------------
def list_templates(registry: ServiceRegistry) -> List[Dict[str, Any]]:
    return registry.events.templates()


def list_events(registry: ServiceRegistry, limit: int = 40) -> List[Dict[str, Any]]:
    events: List[Event] = registry.events.list_events(limit=limit)
    decisions = registry.repository.list_decisions(limit=200)
    by_event: Dict[str, DecisionRun] = {}
    for run in decisions:
        by_event.setdefault(run.event.id, run)

    payload: List[Dict[str, Any]] = []
    for event in events:
        run = by_event.get(event.id)
        item = event.model_dump(mode="json")
        item["analysis_status"] = "pending"
        item["decision"] = None
        if run is not None:
            item["decision"] = {
                "id": run.id,
                "status": run.status,
                "llm_provider": run.llm_provider,
                "risk_status": run.risk.status.value if run.risk else None,
                "confidence": run.analysis.confidence if run.analysis else None,
                "sentiment": run.analysis.sentiment.value if run.analysis else None,
                "trade_count": len(run.trades),
            }
            item["analysis_status"] = (
                "running"
                if run.status == "running"
                else ("failed" if run.status == "failed" else "analysed")
            )
        payload.append(item)
    return payload


def sync_events(
    registry: ServiceRegistry, limit: int = 40, principal: Optional[Principal] = None
) -> Dict[str, Any]:
    who = principal or anonymous()
    registry.guard.check_control(who.ip, "events-sync")
    fresh = registry.events.sync(limit=limit)
    _audit_control(registry, who, "events_sync", f"ingested={len(fresh)} limit={limit}")
    return {
        "ingested": len(fresh),
        "events": [e.model_dump(mode="json") for e in fresh],
    }


# --- agent --------------------------------------------------------------
def _start_guarded_run(
    registry: ServiceRegistry,
    who: Principal,
    action: str,
    *,
    template_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    """Rate-limit, then take the single global agent slot before starting."""

    registry.guard.check_agent(who.ip)
    registry.guard.concurrency.acquire()
    try:
        decision_id = registry.orchestrator.start_run(
            template_key=template_key,
            event_payload=payload,
            on_complete=registry.guard.concurrency.release,
        )
    except BaseException:
        registry.guard.concurrency.release()
        raise
    _audit_control(
        registry,
        who,
        action,
        f"decision={decision_id} template={template_key or 'event_payload'}",
    )
    return decision_id


def simulate_event(
    registry: ServiceRegistry, template_key: str, principal: Optional[Principal] = None
) -> Dict[str, Any]:
    if template_key not in registry.events.template_keys():
        raise KeyError(template_key)
    decision_id = _start_guarded_run(
        registry, principal or anonymous(), "agent_simulate", template_key=template_key
    )
    return {
        "decision_id": decision_id,
        "status": "running",
        "template_key": template_key,
    }


def run_event_payload(
    registry: ServiceRegistry,
    payload: Dict[str, Any],
    principal: Optional[Principal] = None,
) -> Dict[str, Any]:
    decision_id = _start_guarded_run(
        registry, principal or anonymous(), "event_ingested", payload=payload
    )
    return {"decision_id": decision_id, "status": "running"}


def run_sync(
    registry: ServiceRegistry,
    template_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    principal: Optional[Principal] = None,
) -> Dict[str, Any]:
    who = principal or anonymous()
    registry.guard.check_agent(who.ip)
    registry.guard.concurrency.acquire()
    try:
        run = registry.orchestrator.run_sync(
            template_key=template_key, event_payload=payload
        )
    finally:
        registry.guard.concurrency.release()
    if principal is not None:
        _audit_control(
            registry,
            who,
            "agent_run",
            f"decision={run.id} template={template_key or 'event_payload'}",
        )
    return decision_to_dict(run)


def get_decision(
    registry: ServiceRegistry, decision_id: str
) -> Optional[Dict[str, Any]]:
    run = registry.orchestrator.get_run(decision_id)
    return decision_to_dict(run) if run else None


def list_decisions(registry: ServiceRegistry, limit: int = 25) -> List[Dict[str, Any]]:
    runs = registry.orchestrator.list_runs(limit=limit)
    return [decision_to_dict(run) for run in runs]


# --- portfolio ----------------------------------------------------------
def portfolio_view(registry: ServiceRegistry) -> Dict[str, Any]:
    snapshot = registry.portfolio.snapshot(persist=False)
    total_value = snapshot.portfolio_value or 1.0
    positions: List[Dict[str, Any]] = []
    for position in snapshot.positions:
        quote = registry.market.quote(position.symbol)
        weight = position.market_value / total_value * 100.0
        pnl = position.unrealized_pnl
        cost = position.avg_entry_price * position.quantity
        positions.append(
            {
                "symbol": position.symbol,
                "name": quote.name if quote else position.symbol,
                "asset_class": quote.asset_class if quote else "unknown",
                "sector": quote.sector if quote else "",
                "quantity": round(position.quantity, 6),
                "avg_entry_price": round(position.avg_entry_price, 4),
                "last_price": round(position.last_price, 4),
                "change_pct": round(quote.change_pct, 4) if quote else 0.0,
                "market_value": round(position.market_value, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round((pnl / cost) * 100.0, 4) if cost else 0.0,
                "weight_pct": round(weight, 4),
                "conviction": position.conviction,
                "last_signal_id": position.last_signal_id,
            }
        )
    positions.sort(key=lambda p: p["market_value"], reverse=True)

    data = snapshot.model_dump(mode="json")
    data["positions"] = positions
    data["mode"] = "PAPER / DEMO" if registry.settings.demo_mode else "PAPER"
    data["kill_switch"] = registry.repository.get_kill_switch()
    return data


def equity_curve(registry: ServiceRegistry, limit: int = 240) -> List[Dict[str, Any]]:
    return registry.portfolio.equity_curve(limit=limit)


def trade_history(registry: ServiceRegistry, limit: int = 100) -> List[Dict[str, Any]]:
    return registry.execution.trade_blotters(limit=limit)


def market_quotes(registry: ServiceRegistry) -> List[Dict[str, Any]]:
    quotes = getattr(registry.market, "all_quotes", None)
    if callable(quotes):
        return [q.to_dict() for q in quotes()]
    return []


def explain_symbol(registry: ServiceRegistry, symbol: str) -> Dict[str, Any]:
    from backend.services.explainability import why_symbol

    runs = registry.orchestrator.list_runs(limit=25)
    for run in runs:
        answer = why_symbol(run, symbol)
        if answer and any(t.symbol == symbol.upper() for t in run.trades):
            return {
                "symbol": symbol.upper(),
                "decision_id": run.id,
                "explanation": answer,
            }
    return {
        "symbol": symbol.upper(),
        "decision_id": None,
        "explanation": f"No recent Eventra decision touched {symbol.upper()}.",
    }


# --- performance metrics -----------------------------------------------
def performance_metrics(registry: ServiceRegistry) -> Dict[str, Any]:
    from backend.services.metrics_service import MetricsService

    metrics = MetricsService(registry.repository)
    return metrics.compute_all()
