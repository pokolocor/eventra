"""Paper execution: fills, slippage, fees and the kill switch."""

from __future__ import annotations

from backend.models.domain import RiskStatus
from backend.services.execution_service import KillSwitchEngagedError
from backend.tests.support import make_registry, run_template


def test_approved_signal_produces_paper_fills(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "fed_hawkish_hold")
    assert run.risk.status in (RiskStatus.APPROVED, RiskStatus.REDUCED)
    assert run.trades, "expected at least one paper trade"
    for trade in run.trades:
        assert trade.mode == "PAPER"
        assert trade.status == "FILLED"
        assert trade.quantity > 0
        assert trade.notional > 0
        assert trade.fee >= 0
        assert trade.slippage >= 0


def test_trades_are_persisted_to_the_blotter(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "earnings_beat_nvda")
    stored = registry.repository.list_trades(limit=50)
    assert len(stored) == len(run.trades)
    assert {t.id for t in stored} == {t.id for t in run.trades}


def test_rejected_signal_executes_nothing(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "low_confidence_rumour")
    assert run.risk.status == RiskStatus.REJECTED
    assert run.trades == []
    assert registry.repository.list_trades(limit=10) == []


def test_illiquid_signal_is_blocked(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "illiquid_meme_pump")
    assert run.risk.status == RiskStatus.REJECTED
    assert run.risk.checks["liquidity"].value == "FAIL"
    assert run.trades == []


def test_kill_switch_prevents_execution(tmp_path):
    registry = make_registry(tmp_path)
    registry.repository.set_kill_switch(True)
    run = run_template(registry, "cpi_surprise_low")
    assert run.trades == []
    assert run.risk.status == RiskStatus.REJECTED


def test_kill_switch_can_be_released(tmp_path):
    registry = make_registry(tmp_path)
    registry.repository.set_kill_switch(True)
    assert registry.repository.get_kill_switch() is True
    registry.repository.set_kill_switch(False)
    assert registry.repository.get_kill_switch() is False
    run = run_template(registry, "cpi_surprise_low")
    assert run.risk.status in (RiskStatus.APPROVED, RiskStatus.REDUCED)


def test_execution_service_refuses_when_kill_switch_engaged(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "cpi_surprise_low")
    registry.repository.set_kill_switch(True)
    try:
        registry.execution.execute(run.risk, run.signal, "dec_x", run.event.id)
    except KillSwitchEngagedError:
        return
    raise AssertionError("expected KillSwitchEngagedError")


def test_market_advances_after_event(tmp_path):
    registry = make_registry(tmp_path)
    tick_before = registry.repository.load_system().market_tick
    price_before = registry.portfolio.price_of("QQQ")
    run_template(registry, "geopolitical_escalation")
    assert registry.repository.load_system().market_tick == tick_before + 1
    assert registry.portfolio.price_of("QQQ") != price_before


def test_live_trading_is_hard_disabled(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "cpi_surprise_low")
    registry.settings.paper_trading_only = False
    try:
        registry.execution.execute(run.risk, run.signal, "dec_y", run.event.id)
    except RuntimeError:
        return
    finally:
        registry.settings.paper_trading_only = True
    raise AssertionError("execution must refuse when paper_trading_only is disabled")


def test_audit_trail_records_every_stage(tmp_path):
    registry = make_registry(tmp_path)
    run_template(registry, "earnings_beat_nvda")
    actions = {entry["action"] for entry in registry.repository.list_audit(limit=200)}
    assert "event_simulated" in actions
    assert "analysis_validated" in actions
    assert any(a.startswith("signal_") for a in actions)
    assert any(a.startswith("paper_") for a in actions)
