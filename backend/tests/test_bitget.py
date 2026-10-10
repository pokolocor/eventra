"""Bitget Demo integration: transport, symbol mapping, order placement."""

from __future__ import annotations

from backend.models.domain import TradeSide
from backend.services.providers.bitget import (
    BitgetDemoService,
    BitgetOrder,
    MockBitgetTransport,
)
from backend.tests.support import make_settings


def test_not_configured_without_keys(tmp_path):
    settings = make_settings(tmp_path)
    service = BitgetDemoService(settings)
    assert not service.is_configured()
    assert isinstance(service.transport, MockBitgetTransport)


def test_configured_with_keys(tmp_path):
    settings = make_settings(
        tmp_path,
        bitget_api_key="test_key",
        bitget_api_secret="test_secret",
        bitget_passphrase="test_pass",
    )
    service = BitgetDemoService(settings)
    assert service.is_configured()


def test_health_check_not_configured(tmp_path):
    settings = make_settings(tmp_path)
    service = BitgetDemoService(settings)
    health = service.health_check()
    assert health["status"] == "not_configured"
    assert health["demo_mode"] is True


def test_health_check_with_mock(tmp_path):
    settings = make_settings(
        tmp_path,
        bitget_api_key="test_key",
        bitget_api_secret="test_secret",
        bitget_passphrase="test_pass",
    )
    mock = MockBitgetTransport()
    service = BitgetDemoService(settings, transport=mock)
    health = service.health_check()
    assert health["status"] == "connected"
    assert health["total_balance"] == 100_000.0
    assert health["demo_mode"] is True


def test_map_crypto_symbols(tmp_path):
    settings = make_settings(tmp_path)
    service = BitgetDemoService(settings)
    assert service._map_symbol("BTC") == "BTCUSDT"
    assert service._map_symbol("ETH") == "ETHUSDT"
    assert service._map_symbol("SOL") == "SOLUSDT"


def test_map_non_crypto_returns_none(tmp_path):
    settings = make_settings(tmp_path)
    service = BitgetDemoService(settings)
    assert service._map_symbol("AAPL") is None
    assert service._map_symbol("SPY") is None
    assert service._map_symbol("QQQ") is None


def test_mock_order_placement(tmp_path):
    settings = make_settings(tmp_path)
    service = BitgetDemoService(settings)
    order = service.place_order("BTC", TradeSide.BUY, 0.1, 50000.0)
    assert isinstance(order, BitgetOrder)
    assert order.status == "filled"
    assert order.symbol == "BTC"
    assert order.size == 0.1


def test_non_crypto_order_is_skipped(tmp_path):
    settings = make_settings(
        tmp_path,
        bitget_api_key="test_key",
        bitget_api_secret="test_secret",
        bitget_passphrase="test_pass",
    )
    mock = MockBitgetTransport()
    service = BitgetDemoService(settings, transport=mock)
    order = service.place_order("AAPL", TradeSide.BUY, 10, 150.0)
    assert order.status == "skipped"


def test_mock_transport_account_response():
    mock = MockBitgetTransport()
    data = mock.request("GET", "/api/v2/mix/account/accounts")
    assert "totalBalance" in data
    assert float(data["totalBalance"]) == 100_000.0


def test_mock_transport_order_response():
    mock = MockBitgetTransport()
    data = mock.request(
        "POST",
        "/api/v2/mix/order/place-order",
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "size": "0.1",
            "price": "50000",
        },
    )
    assert "orderId" in data
    assert data["status"] == "filled"
    assert len(mock.orders) == 1
