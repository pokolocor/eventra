"""Deterministic risk engine: limits, sizing, rejections and the kill switch."""

from __future__ import annotations

import uuid
from typing import List, Tuple

from backend.models.domain import (
    AssetImpact,
    Direction,
    MarketRegime,
    PortfolioActionProposal,
    RecommendedAction,
    RiskStatus,
    Sentiment,
    Signal,
    TimeHorizon,
)
from backend.services.providers.market_data import Instrument
from backend.tests.support import make_registry, run_template


def make_signal(
    actions: List[Tuple[str, str, float]],
    confidence: float = 0.85,
    impacts: List[Tuple[str, str, int]] | None = None,
) -> Signal:
    return Signal(
        id=f"sig_{uuid.uuid4().hex[:8]}",
        event_id="evt_test",
        sentiment=Sentiment.BEARISH,
        market_regime=MarketRegime.RISK_OFF,
        recommended_action=RecommendedAction.REDUCE_RISK,
        confidence=confidence,
        time_horizon=TimeHorizon.SHORT,
        affected_assets=[
            AssetImpact(symbol=s, direction=Direction(d), impact_score=i)
            for s, d, i in (impacts or [(a[0], "negative", 70) for a in actions])
        ],
        proposed_actions=[
            PortfolioActionProposal(symbol=s, action=a, percentage=p) for s, a, p in actions
        ],
        reasoning_summary="Unit-test signal.",
    )


def test_kill_switch_blocks_everything(tmp_path):
    registry = make_registry(tmp_path)
    registry.repository.set_kill_switch(True)
    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 5)]))
    assert decision.status == RiskStatus.REJECTED
    assert decision.kill_switch_engaged is True
    assert decision.checks["kill_switch"].value == "FAIL"
    assert decision.approved_actions == []


def test_kill_switch_blocks_execution_not_just_risk(tmp_path):
    registry = make_registry(tmp_path)
    registry.repository.set_kill_switch(True)
    run = run_template(registry, "fed_hawkish_hold")
    assert run.trades == []
    assert run.risk.status == RiskStatus.REJECTED
    assert any("kill switch" in r.lower() for r in run.risk.reasons)


def test_low_confidence_is_rejected(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 5)], confidence=0.31))
    assert decision.status == RiskStatus.REJECTED
    assert decision.checks["confidence_threshold"].value == "FAIL"


def test_confidence_at_threshold_passes(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 5)], confidence=0.60))
    assert decision.checks["confidence_threshold"].value == "PASS"


def test_illiquid_asset_is_rejected(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("ILLIQ", "BUY", 5)], confidence=0.95))
    assert decision.status == RiskStatus.REJECTED
    assert decision.checks["liquidity"].value == "FAIL"


def test_excessive_volatility_is_rejected(tmp_path):
    registry = make_registry(tmp_path)
    registry.market.universe["VOLX"] = Instrument(
        symbol="VOLX", name="Volatile Demo", asset_class="equity", base_price=50.0,
        annualized_vol=1.40, avg_daily_volume_usd=5_000_000_000, sector="test",
    )
    decision = registry.risk_engine.evaluate(make_signal([("VOLX", "BUY", 5)], confidence=0.9))
    assert decision.status == RiskStatus.REJECTED
    assert decision.checks["volatility"].value == "FAIL"


def test_position_limit_caps_single_name_add(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "INCREASE", 30)], confidence=0.9))
    assert decision.status == RiskStatus.REDUCED
    assert decision.checks["position_limit"].value in ("WARN", "FAIL")
    approved = decision.approved_actions[0]
    assert approved.percentage < 30
    snapshot = registry.portfolio.snapshot(persist=False)
    projected = registry.portfolio.target_notional_for("QQQ", approved.action, approved.percentage, snapshot)
    weight = (
        next(p.market_value for p in snapshot.positions if p.symbol == "QQQ") + projected
    ) / snapshot.portfolio_value * 100
    assert weight <= registry.settings.risk_limits.max_position_weight_pct + 0.5


def test_max_trade_notional_caps_size(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("NVDA", "INCREASE", 20)], confidence=0.9))
    assert decision.checks["max_trade_size"].value == "WARN"
    assert decision.status == RiskStatus.REDUCED
    assert decision.approved_actions[0].percentage < 20
    snapshot = registry.portfolio.snapshot(persist=False)
    notional = registry.portfolio.target_notional_for(
        "NVDA", decision.approved_actions[0].action, decision.approved_actions[0].percentage, snapshot
    )
    limits = registry.settings.risk_limits
    assert notional <= max(limits.max_trade_notional, snapshot.portfolio_value * limits.max_single_trade_pct / 100) + 1


def test_unknown_symbol_is_dropped(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("NOTREAL", "BUY", 5)], confidence=0.9))
    assert decision.status == RiskStatus.REJECTED
    assert decision.checks["portfolio_rules"].value == "FAIL"


def test_reduce_without_position_is_dropped(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("ETH", "REDUCE", 10)], confidence=0.9))
    assert decision.status == RiskStatus.REJECTED
    assert any("not held" in r for r in decision.reasons)


def test_gross_exposure_cap_reduces_buys(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(
        make_signal(
            [("NVDA", "INCREASE", 12), ("MSFT", "INCREASE", 10), ("JPM", "INCREASE", 10), ("GLD", "INCREASE", 8)],
            confidence=0.9,
        )
    )
    assert decision.status == RiskStatus.REDUCED
    assert decision.checks["portfolio_exposure"].value == "WARN"
    assert decision.scale_factor < 1.0


def test_duplicate_signal_within_cooldown_is_dropped(tmp_path):
    registry = make_registry(tmp_path)
    signal = make_signal([("QQQ", "REDUCE", 4)], confidence=0.9)
    first = registry.risk_engine.evaluate(signal)
    assert first.status == RiskStatus.APPROVED
    registry.risk_engine.record_executed_signal(signal, "dec_test")

    second = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 4)], confidence=0.9))
    assert second.status == RiskStatus.REJECTED
    assert second.checks["duplicate_signal"].value == "FAIL"


def test_duplicate_cooldown_only_affects_same_direction(tmp_path):
    registry = make_registry(tmp_path)
    signal = make_signal([("QQQ", "REDUCE", 4)], confidence=0.9)
    registry.risk_engine.evaluate(signal)
    registry.risk_engine.record_executed_signal(signal, "dec_test")

    opposite = registry.risk_engine.evaluate(make_signal([("QQQ", "INCREASE", 4)], confidence=0.9))
    assert opposite.status in (RiskStatus.APPROVED, RiskStatus.REDUCED)


def test_daily_loss_limit_halts_trading(tmp_path):
    registry = make_registry(tmp_path)
    state = registry.repository.load_portfolio()
    snapshot = registry.portfolio.snapshot(persist=False)
    state.day_start_value = snapshot.portfolio_value * 1.10  # pretend we are down 9%
    registry.repository.save_portfolio(state)

    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 5)], confidence=0.9))
    assert decision.status == RiskStatus.REJECTED
    assert decision.checks["daily_loss_limit"].value == "FAIL"


def test_decision_payload_matches_documented_shape(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(make_signal([("QQQ", "REDUCE", 5)], confidence=0.9))
    payload = decision.to_public_dict()
    assert payload["status"] in {"APPROVED", "REJECTED", "REDUCED"}
    assert payload["checks"]["position_limit"] in {"PASS", "WARN", "FAIL"}
    assert payload["checks"]["liquidity"] in {"PASS", "WARN", "FAIL"}
    assert payload["checks"]["volatility"] in {"PASS", "WARN", "FAIL"}
    assert payload["checks"]["daily_loss_limit"] in {"PASS", "WARN", "FAIL"}


def test_actions_capped_per_decision(tmp_path):
    registry = make_registry(tmp_path)
    registry.settings.risk_limits.max_actions_per_decision = 2
    decision = registry.risk_engine.evaluate(
        make_signal(
            [("QQQ", "REDUCE", 2), ("SPY", "REDUCE", 2), ("GLD", "INCREASE", 2), ("NVDA", "INCREASE", 2)],
            confidence=0.9,
        )
    )
    assert len(decision.approved_actions) <= 2


def test_partial_drop_is_reported_as_reduced_not_approved(tmp_path):
    registry = make_registry(tmp_path)
    decision = registry.risk_engine.evaluate(
        make_signal([("QQQ", "REDUCE", 5), ("NOTREAL", "BUY", 5)], confidence=0.9)
    )
    assert decision.checks["portfolio_rules"].value == "FAIL"
    assert decision.status == RiskStatus.REDUCED
    assert [action.symbol for action in decision.approved_actions] == ["QQQ"]


def test_no_failed_check_is_ever_approved(tmp_path):
    registry = make_registry(tmp_path)
    for key in registry.events.template_keys():
        run = run_template(registry, key)
        assert run.risk is not None
        failed = [name for name, value in run.risk.checks.items() if value.value == "FAIL"]
        if failed:
            assert run.risk.status != RiskStatus.APPROVED, f"{key} approved with failing checks {failed}"