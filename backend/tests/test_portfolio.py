"""Paper portfolio maths: fills, average cost, PnL and exposure."""

from __future__ import annotations

from backend.models.domain import TradeAction, TradeSide
from backend.services.portfolio_service import (
    InsufficientFundsError,
    InsufficientPositionError,
)
from backend.tests.support import make_registry, portfolio_dict


def test_seed_produces_a_funded_book(tmp_path):
    registry = make_registry(tmp_path)
    snapshot = registry.portfolio.snapshot(persist=False)
    assert snapshot.starting_balance == registry.settings.starting_balance
    assert snapshot.cash > 0
    assert len(snapshot.positions) >= 6
    assert 0 < snapshot.exposure < 100
    assert abs(snapshot.portfolio_value - snapshot.starting_balance) < snapshot.starting_balance * 0.05


def test_buy_updates_cash_and_average_entry(tmp_path):
    registry = make_registry(tmp_path)
    before = registry.portfolio.snapshot(persist=False)
    price = registry.portfolio.price_of("SPY")
    position_before = next(p for p in before.positions if p.symbol == "SPY")

    trade = registry.portfolio.execute(
        symbol="SPY", side=TradeSide.BUY, quantity=100, price=price,
        action=TradeAction.INCREASE, reason="test", decision_id="dec_1",
    )

    after = registry.portfolio.snapshot(persist=False)
    position_after = next(p for p in after.positions if p.symbol == "SPY")
    assert trade.mode == "PAPER"
    assert trade.status == "FILLED"
    assert position_after.quantity == position_before.quantity + 100
    assert after.cash < before.cash
    expected_entry = (
        position_before.avg_entry_price * position_before.quantity + price * 100
    ) / (position_before.quantity + 100)
    assert abs(position_after.avg_entry_price - expected_entry) < 1e-6


def test_sell_realises_pnl(tmp_path):
    registry = make_registry(tmp_path)
    price = registry.portfolio.price_of("QQQ")
    registry.portfolio.execute(
        symbol="QQQ", side=TradeSide.BUY, quantity=10, price=price,
        action=TradeAction.INCREASE, reason="seed test buy",
    )
    state = registry.repository.load_portfolio()
    entry = state.positions["QQQ"].avg_entry_price

    trade = registry.portfolio.execute(
        symbol="QQQ", side=TradeSide.SELL, quantity=10, price=entry + 5.0,
        action=TradeAction.REDUCE, reason="take profit",
    )
    assert trade.realized_pnl > 0
    assert abs(trade.realized_pnl - 50.0) < 0.01
    assert registry.repository.load_portfolio().realized_pnl > 0


def test_cannot_spend_cash_that_does_not_exist(tmp_path):
    registry = make_registry(tmp_path)
    cash = registry.repository.load_portfolio().cash
    try:
        registry.portfolio.execute(
            symbol="SPY", side=TradeSide.BUY, quantity=10_000, price=cash,
            action=TradeAction.BUY, reason="impossible",
        )
    except InsufficientFundsError:
        return
    raise AssertionError("expected InsufficientFundsError")


def test_cannot_sell_more_than_held(tmp_path):
    registry = make_registry(tmp_path)
    try:
        registry.portfolio.execute(
            symbol="SPY", side=TradeSide.SELL, quantity=10_000, price=100.0,
            action=TradeAction.SELL, reason="impossible",
        )
    except InsufficientPositionError:
        return
    raise AssertionError("expected InsufficientPositionError")


def test_full_exit_removes_position(tmp_path):
    registry = make_registry(tmp_path)
    held = registry.repository.load_portfolio().positions["JPM"].quantity
    registry.portfolio.execute(
        symbol="JPM", side=TradeSide.SELL, quantity=held, price=registry.portfolio.price_of("JPM"),
        action=TradeAction.SELL, reason="full exit",
    )
    assert "JPM" not in registry.repository.load_portfolio().positions


def test_exposure_moves_with_trades(tmp_path):
    registry = make_registry(tmp_path)
    before = registry.portfolio.snapshot(persist=False).exposure
    registry.portfolio.execute(
        symbol="SPY", side=TradeSide.SELL,
        quantity=registry.repository.load_portfolio().positions["SPY"].quantity,
        price=registry.portfolio.price_of("SPY"), action=TradeAction.SELL, reason="de-risk",
    )
    after = registry.portfolio.snapshot(persist=False).exposure
    assert after < before


def test_portfolio_view_is_api_shaped(tmp_path):
    registry = make_registry(tmp_path)
    view = portfolio_dict(registry)
    assert view["mode"] == "PAPER / DEMO"
    assert "portfolio_value" in view and "positions" in view
    row = view["positions"][0]
    for key in ("symbol", "quantity", "avg_entry_price", "last_price",
                "unrealized_pnl", "weight_pct", "conviction"):
        assert key in row


def test_equity_curve_is_seeded(tmp_path):
    registry = make_registry(tmp_path)
    curve = registry.portfolio.equity_curve(limit=200)
    assert len(curve) > 20
    assert all(point["portfolio_value"] > 0 for point in curve)
