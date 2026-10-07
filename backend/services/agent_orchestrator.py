"""Agent orchestrator - the Eventra decision pipeline.

    Event -> Qwen interpretation -> Market impact -> Signal
          -> Risk check -> Paper execution -> Portfolio update

Runs synchronously (`run_sync`, used by tests) or in a worker thread
(`start_run`, used by the API so the dashboard can watch the chain build up in
real time). Every stage appends a `TimelineEntry` and an audit record.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.config import Settings
from backend.database.repository import Repository
from backend.models.domain import (
    DecisionRun,
    Event,
    PipelineStage,
    QwenAnalysis,
    RiskStatus,
    Signal,
    TimelineEntry,
    utcnow,
)
from backend.services.event_service import EventService
from backend.services.execution_service import ExecutionService
from backend.services.portfolio_service import PortfolioService
from backend.services.qwen_service import QwenServiceError, QwenUnavailableError
from backend.services.risk_engine import RiskEngine


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class AgentOrchestrator:
    def __init__(
        self,
        events: EventService,
        portfolio: PortfolioService,
        risk_engine: RiskEngine,
        execution: ExecutionService,
        repository: Repository,
        settings: Settings,
        llm_resolver: Callable[[], Any],
        stage_delay_ms: int = 0,
    ) -> None:
        self.events = events
        self.portfolio = portfolio
        self.risk_engine = risk_engine
        self.execution = execution
        self.repository = repository
        self.settings = settings
        self.llm_resolver = llm_resolver
        self.stage_delay_ms = max(0, int(stage_delay_ms))
        self._runs: Dict[str, DecisionRun] = {}
        self._lock = threading.RLock()

    # --- public API -----------------------------------------------------
    def start_run(
        self,
        template_key: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        decision_id = _id("dec")
        run = DecisionRun(id=decision_id, event=self._placeholder_event(decision_id), status="running")
        with self._lock:
            self._runs[decision_id] = run

        worker = threading.Thread(
            target=self._worker,
            args=(decision_id, template_key, event_payload),
            name=f"eventra-{decision_id}",
            daemon=True,
        )
        worker.start()
        return decision_id

    def _worker(
        self,
        decision_id: str,
        template_key: Optional[str],
        event_payload: Optional[Dict[str, Any]],
    ) -> None:
        try:
            self.run_sync(decision_id=decision_id, template_key=template_key, event_payload=event_payload)
        except Exception as exc:  # pragma: no cover - defensive
            with self._lock:
                run = self._runs.get(decision_id)
                if run is not None:
                    run.status = "failed"
                    run.error = f"{type(exc).__name__}: {exc}"
                    run.timeline.append(
                        TimelineEntry(
                            stage=PipelineStage.EXECUTION,
                            title="Pipeline aborted",
                            detail=run.error,
                            status="error",
                        )
                    )
                    self.repository.save_decision(run)

    def get_run(self, decision_id: str) -> Optional[DecisionRun]:
        with self._lock:
            run = self._runs.get(decision_id)
            if run is not None:
                return run.model_copy(deep=True)
        return self.repository.get_decision(decision_id)

    def list_runs(self, limit: int = 25) -> List[DecisionRun]:
        return self.repository.list_decisions(limit=limit)

    def run_sync(
        self,
        template_key: Optional[str] = None,
        event_payload: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
    ) -> DecisionRun:
        decision_id = decision_id or _id("dec")
        event, template = self._resolve_event(template_key, event_payload, decision_id)

        run = DecisionRun(
            id=decision_id,
            event=event,
            status="running",
            llm_provider="pending",
            mode="PAPER / DEMO" if self.settings.demo_mode else "PAPER",
        )
        self._publish(run)
        self._stage(run, PipelineStage.EVENT_DETECTED, "Event detected", 
                    f"{event.title} [{event.importance.value.upper()}] via {event.source}",
                    payload={"event_id": event.id, "category": event.category.value})

        analysis = self._stage_analysis(run, event)
        if analysis is None:
            run.status = "failed"
            self._finish(run)
            return run

        self._stage_impact(run, analysis, template)
        signal = self._stage_signal(run, event, analysis)
        risk = self._stage_risk(run, signal)
        self._stage_execution(run, signal, risk, event)
        self._stage_portfolio(run)

        run.status = "completed"
        self._finish(run)
        return run

    # --- stages ---------------------------------------------------------
    def _resolve_event(
        self,
        template_key: Optional[str],
        event_payload: Optional[Dict[str, Any]],
        decision_id: str,
    ) -> Any:
        if template_key:
            event, template = self.events.simulate(template_key)
            return event, template
        if event_payload:
            event = self.events.normalise(event_payload)
            self.repository.save_event(event)
            return event, self.events.get_template(event.template_key or "")
        existing = self.events.get_event(decision_id)
        if existing is not None:
            return existing, self.events.get_template(existing.template_key or "")
        raise ValueError("run_sync requires template_key or event_payload")

    def _stage_analysis(self, run: DecisionRun, event: Event) -> Optional[QwenAnalysis]:
        service, mode = self.llm_resolver()
        started = time.perf_counter()
        try:
            analysis = service.analyze_event(event)
        except QwenUnavailableError as exc:
            run.llm_provider = "demo-mock"
            self._stage(
                run,
                PipelineStage.QWEN_ANALYSIS,
                "Qwen unavailable - Demo Mode engaged",
                str(exc),
                status="warning",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            analysis = self._demo_fallback(event)
            if analysis is None:
                return None
        except QwenServiceError as exc:
            run.llm_provider = mode
            run.error = f"{type(exc).__name__}: {exc}"
            self._stage(
                run,
                PipelineStage.QWEN_ANALYSIS,
                "Qwen analysis failed",
                run.error,
                status="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return None

        run.llm_provider = getattr(analysis, "provider", mode)
        run.analysis = analysis
        self._stage(
            run,
            PipelineStage.QWEN_ANALYSIS,
            f"Qwen analysis complete ({run.llm_provider})",
            (
                f"{analysis.event_type.replace('_', ' ')} | {analysis.sentiment.value} | "
                f"{analysis.market_regime.value.replace('_', '-')} | confidence {analysis.confidence:.0%} | "
                f"{analysis.model}"
            ),
            duration_ms=analysis.latency_ms or int((time.perf_counter() - started) * 1000),
            payload=analysis.model_dump(mode="json", exclude={"raw_output"}),
        )
        self.repository.audit(
            "qwen_service",
            "analysis_validated",
            f"event={event.id} sentiment={analysis.sentiment.value} confidence={analysis.confidence:.2f}",
        )
        return analysis

    def _demo_fallback(self, event: Event) -> Optional[QwenAnalysis]:
        if not self.settings.demo_mode:
            return None
        from backend.services.demo_llm import DemoLLMService

        analysis = DemoLLMService().analyze_event(event)
        return analysis

    def _stage_impact(self, run: DecisionRun, analysis: QwenAnalysis, template: Any) -> None:
        shocks: Dict[str, float] = {}
        if template is not None and getattr(template, "price_shocks", None):
            shocks = dict(template.price_shocks)
        else:
            for asset in analysis.affected_assets:
                magnitude = (asset.impact_score / 100.0) * 0.02
                shocks[asset.symbol] = magnitude if asset.direction.value == "positive" else -magnitude
        tick = self.execution.advance_market(shocks)

        ranked = sorted(analysis.affected_assets, key=lambda a: a.impact_score, reverse=True)
        detail = ", ".join(
            f"{a.symbol} {a.direction.value} {a.impact_score}" for a in ranked[:6]
        )
        self._stage(
            run,
            PipelineStage.MARKET_IMPACT,
            "Market impact estimated",
            f"{len(ranked)} assets scored. {detail}. Simulated tape advanced to tick {tick}.",
            payload={
                "impacts": [a.model_dump(mode="json") for a in ranked],
                "market_tick": tick,
                "shocks_applied": shocks,
            },
        )

    def _stage_signal(self, run: DecisionRun, event: Event, analysis: QwenAnalysis) -> Signal:
        signal = Signal(
            id=_id("sig"),
            event_id=event.id,
            created_at=utcnow(),
            sentiment=analysis.sentiment,
            market_regime=analysis.market_regime,
            recommended_action=analysis.recommended_action,
            confidence=analysis.confidence,
            time_horizon=analysis.time_horizon,
            affected_assets=analysis.affected_assets,
            proposed_actions=analysis.portfolio_actions,
            reasoning_summary=analysis.reasoning_summary,
            provider=analysis.provider,
            model=analysis.model,
        )
        run.signal = signal
        actions = ", ".join(
            f"{a.action.value} {a.symbol} {a.percentage:g}%" for a in signal.proposed_actions
        ) or "no change"
        self._stage(
            run,
            PipelineStage.SIGNAL_GENERATED,
            "Signal generated",
            f"{signal.recommended_action.value.replace('_', ' ').upper()} | horizon {signal.time_horizon.value} "
            f"| proposed: {actions}",
            payload=signal.model_dump(mode="json"),
        )
        return signal

    def _stage_risk(self, run: DecisionRun, signal: Signal) -> Any:
        risk = self.risk_engine.evaluate(signal)
        run.risk = risk
        failed = [name for name, result in risk.checks.items() if result.value == "FAIL"]
        warned = [name for name, result in risk.checks.items() if result.value == "WARN"]
        detail = f"{risk.status.value}"
        if failed:
            detail += f" | failed: {', '.join(failed)}"
        if warned:
            detail += f" | warnings: {', '.join(warned)}"
        if risk.reasons:
            detail += f" | {risk.reasons[0]}"
        self._stage(
            run,
            PipelineStage.RISK_CHECK,
            f"Risk engine: {risk.status.value}",
            detail,
            status="success" if risk.status == RiskStatus.APPROVED else (
                "warning" if risk.status == RiskStatus.REDUCED else "error"
            ),
            payload=risk.to_public_dict(),
        )
        self.repository.audit(
            "risk_engine",
            f"signal_{risk.status.value.lower()}",
            f"signal={signal.id} checks_failed={failed} scale={risk.scale_factor:.2f}",
        )
        return risk

    def _stage_execution(self, run: DecisionRun, signal: Signal, risk: Any, event: Event) -> None:
        if risk.status == RiskStatus.REJECTED:
            self._stage(
                run,
                PipelineStage.EXECUTION,
                "Execution blocked by risk engine",
                "PAPER TRADE NOT EXECUTED - the proposal never reached the simulator.",
                status="error",
                payload={"executed": False, "trades": []},
            )
            self.repository.audit("execution_service", "execution_blocked", f"decision={run.id}")
            return

        trades = self.execution.execute(risk, signal, run.id, event.id)
        run.trades = trades
        self.risk_engine.record_executed_signal(signal, run.id)

        if not trades:
            self._stage(
                run,
                PipelineStage.EXECUTION,
                "No trade required",
                "Risk engine approved the signal but every action sized to zero; portfolio unchanged.",
                status="warning",
                payload={"executed": False, "trades": []},
            )
            return

        detail = ", ".join(
            f"{t.action.value} {t.quantity:,.4f} {t.symbol} @ ${t.price:,.2f}" for t in trades
        )
        self._stage(
            run,
            PipelineStage.EXECUTION,
            f"PAPER TRADE EXECUTED ({len(trades)} fill{'s' if len(trades) != 1 else ''})",
            detail,
            payload={"executed": True, "trades": [t.model_dump(mode="json") for t in trades]},
        )

    def _stage_portfolio(self, run: DecisionRun) -> None:
        snapshot = self.portfolio.snapshot()
        run.portfolio_after = snapshot
        direction = "up" if snapshot.day_pnl >= 0 else "down"
        self._stage(
            run,
            PipelineStage.PORTFOLIO_UPDATED,
            "Portfolio updated",
            (
                f"Value ${snapshot.portfolio_value:,.2f} ({direction} ${abs(snapshot.day_pnl):,.2f} today) | "
                f"exposure {snapshot.exposure:.1f}% | {len(snapshot.positions)} open positions | "
                f"realised PnL ${snapshot.realized_pnl:,.2f}"
            ),
            payload=snapshot.model_dump(mode="json"),
        )

    # --- plumbing -------------------------------------------------------
    def _stage(
        self,
        run: DecisionRun,
        stage: PipelineStage,
        title: str,
        detail: str = "",
        status: str = "success",
        duration_ms: int = 0,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = TimelineEntry(
            stage=stage,
            title=title,
            detail=detail,
            status=status,
            timestamp=utcnow(),
            duration_ms=int(duration_ms),
            payload=payload or {},
        )
        run.timeline.append(entry)
        self._publish(run)
        if self.stage_delay_ms:
            time.sleep(self.stage_delay_ms / 1000.0)

    def _publish(self, run: DecisionRun) -> None:
        with self._lock:
            self._runs[run.id] = run.model_copy(deep=True)

    def _finish(self, run: DecisionRun) -> None:
        from backend.services.explainability import explain_decision

        run.explanation = explain_decision(run)
        self.repository.save_decision(run)
        self._publish(run)
        self.repository.audit(
            "orchestrator",
            f"decision_{run.status}",
            f"id={run.id} event={run.event.id} trades={len(run.trades)} risk="
            f"{run.risk.status.value if run.risk else 'n/a'}",
        )

    def _placeholder_event(self, decision_id: str) -> Event:
        return Event(
            id=f"pending_{decision_id}",
            timestamp=datetime.now(timezone.utc),
            title="Preparing event...",
            source="eventra",
            summary="",
        )
