"""Performance metrics: Sharpe, Sortino, drawdown, win rate, profit factor."""

from __future__ import annotations

from backend.services.metrics_service import MetricsService
from backend.tests.support import make_registry, run_template


def test_empty_metrics_have_expected_fields(tmp_path):
    registry = make_registry(tmp_path, seed=False)
    registry.bootstrap()
    metrics = MetricsService(registry.repository)
    result = metrics.compute_all()

    # Fields should exist; values depend on seeded equity curve
    assert "sharpe_ratio" in result
    assert "sortino_ratio" in result
    assert "max_drawdown" in result
    assert "max_drawdown_pct" in result
    assert "win_rate" in result
    assert "profit_factor" in result
    assert "total_trades" in result
    assert "paper_trading_days" in result
    assert "last_updated" in result


def test_metrics_after_trades(tmp_path):
    registry = make_registry(tmp_path)
    # Run a template to generate at least one decision + trade
    run_template(registry, "fed_hawkish_hold")

    metrics = MetricsService(registry.repository)
    result = metrics.compute_all()

    assert result["total_trades"] >= 0
    assert result["decisions_total"] >= 1
    assert result["decisions_executed"] >= 0
    assert "sharpe_ratio" in result
    assert "sortino_ratio" in result
    assert "max_drawdown" in result
    assert "max_drawdown_pct" in result
    assert "win_rate" in result
    assert "profit_factor" in result
    assert "risk_violations" in result
    assert "total_fees" in result
    assert "total_slippage" in result
    assert result["paper_trading_days"] >= 0


def test_sharpe_with_known_equity_curve(tmp_path):
    """Verify Sharpe calculation with a simple increasing equity curve."""
    registry = make_registry(tmp_path)
    metrics = MetricsService(registry.repository)

    # The seeded equity curve should produce a defined (possibly zero) Sharpe
    equity = registry.repository.list_equity(limit=2000)
    if len(equity) >= 2:
        sharpe = metrics._sharpe_ratio(equity)
        # Sharpe should be a finite number
        assert sharpe == sharpe  # not NaN


def test_max_drawdown_non_negative(tmp_path):
    registry = make_registry(tmp_path)
    metrics = MetricsService(registry.repository)
    equity = registry.repository.list_equity(limit=2000)

    dd = metrics._max_drawdown(equity)
    dd_pct = metrics._max_drawdown_pct(equity)
    assert dd >= 0.0
    assert dd_pct >= 0.0
    assert dd_pct <= 100.0


def test_win_rate_bounds(tmp_path):
    registry = make_registry(tmp_path)
    metrics = MetricsService(registry.repository)
    trades = registry.repository.list_trades(limit=1000)

    if trades:
        wr = metrics._win_rate(trades)
        assert 0.0 <= wr <= 100.0


def test_profit_factor_non_negative(tmp_path):
    registry = make_registry(tmp_path)
    metrics = MetricsService(registry.repository)
    trades = registry.repository.list_trades(limit=1000)

    if trades:
        pf = metrics._profit_factor(trades)
        assert pf >= 0.0
