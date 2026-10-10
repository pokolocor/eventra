"""Bitget Demo trading integration.

Connects Eventra's paper trades to Bitget's demo trading environment.
Uses the Bitget V2 API for demo account operations.

Reference: https://www.bitget.com/api-doc/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol
from urllib.parse import urlencode

from backend.config import Settings
from backend.models.domain import TradeSide
from backend.observability import get_logger

logger = get_logger("bitget")


class BitgetOrder:
    """Represents a Bitget demo order."""

    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        size: float,
        price: float,
        order_type: str = "limit",
        status: str = "pending",
        created_at: Optional[datetime] = None,
    ) -> None:
        self.order_id = order_id
        self.symbol = symbol
        self.side = side  # "buy" or "sell"
        self.size = size
        self.price = price
        self.order_type = order_type
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "price": self.price,
            "order_type": self.order_type,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class BitgetAccountInfo:
    """Bitget demo account information."""

    def __init__(
        self,
        total_balance: float,
        available_balance: float,
        unrealized_pnl: float,
        margin_ratio: float,
        positions: List[Dict[str, Any]],
    ) -> None:
        self.total_balance = total_balance
        self.available_balance = available_balance
        self.unrealized_pnl = unrealized_pnl
        self.margin_ratio = margin_ratio
        self.positions = positions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_balance": self.total_balance,
            "available_balance": self.available_balance,
            "unrealized_pnl": self.unrealized_pnl,
            "margin_ratio": self.margin_ratio,
            "positions": self.positions,
        }


class BitgetTransport(Protocol):
    """Transport protocol for Bitget API calls."""

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...


class BitgetDemoTransport:
    """Real Bitget API transport for demo trading."""

    BASE_URL = "https://api.bitget.com"

    def __init__(self, api_key: str, api_secret: str, passphrase: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate Bitget API signature."""
        message = timestamp + method.upper() + path + body
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return b64encode(mac.digest()).decode("utf-8")

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to Bitget API."""
        import requests

        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(body) if body else ""
        signature = self._sign(timestamp, method, path, body_str)

        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

        url = f"{self.BASE_URL}{path}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(
                    url, headers=headers, data=body_str, timeout=10
                )

            data = response.json()

            if data.get("code") != "00000":
                logger.error(
                    "bitget_api_error",
                    extra={
                        "extra_fields": {
                            "path": path,
                            "code": data.get("code"),
                            "msg": data.get("msg"),
                        }
                    },
                )
                raise RuntimeError(
                    f"Bitget API error: {data.get('msg', 'Unknown error')}"
                )

            return data.get("data", {})

        except requests.exceptions.RequestException as exc:
            logger.error(
                "bitget_request_failed",
                extra={"extra_fields": {"path": path, "error": str(exc)}},
            )
            raise


class MockBitgetTransport:
    """Mock transport for testing without real API calls."""

    def __init__(self) -> None:
        self.orders: List[BitgetOrder] = []
        self.balance = 100_000.0
        self.positions: List[Dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Mock API responses."""
        if "/account" in path:
            return {
                "totalBalance": str(self.balance),
                "availableBalance": str(self.balance * 0.8),
                "unrealizedPL": "0.0",
                "marginRatio": "0.5",
            }
        elif "/order" in path and method.upper() == "POST":
            order_id = f"bitget_{int(time.time() * 1000)}"
            order = BitgetOrder(
                order_id=order_id,
                symbol=body.get("symbol", "BTCUSDT"),
                side=body.get("side", "buy"),
                size=float(body.get("size", 0)),
                price=float(body.get("price", 0)),
                status="filled",
            )
            self.orders.append(order)
            return {"orderId": order_id, "status": "filled"}
        elif "/positions" in path:
            return {"positions": self.positions}
        return {}


class BitgetUnavailableError(Exception):
    """Raised when Bitget is not configured or unreachable."""

    pass


class BitgetDemoService:
    """Bitget Demo trading service.

    Connects Eventra to Bitget's demo trading environment.
    All trades are simulated with virtual funds.
    """

    def __init__(
        self,
        settings: Settings,
        transport: Optional[BitgetTransport] = None,
    ) -> None:
        self.settings = settings
        self.enabled = bool(settings.bitget_api_key and settings.bitget_api_secret)

        if transport is not None:
            self.transport = transport
        elif self.enabled:
            self.transport = BitgetDemoTransport(
                api_key=settings.bitget_api_key,
                api_secret=settings.bitget_api_secret,
                passphrase=settings.bitget_passphrase,
            )
        else:
            self.transport = MockBitgetTransport()

        self._last_account_info: Optional[BitgetAccountInfo] = None

    # --- account --------------------------------------------------------
    def get_account_info(self) -> BitgetAccountInfo:
        """Fetch demo account balance and positions."""
        if not self.enabled and isinstance(self.transport, MockBitgetTransport):
            return BitgetAccountInfo(
                total_balance=self.transport.balance,
                available_balance=self.transport.balance * 0.8,
                unrealized_pnl=0.0,
                margin_ratio=0.5,
                positions=[],
            )

        try:
            data = self.transport.request("GET", "/api/v2/mix/account/accounts")

            positions = []
            try:
                pos_data = self.transport.request(
                    "GET", "/api/v2/mix/position/all-position"
                )
                positions = pos_data if isinstance(pos_data, list) else []
            except Exception:
                pass

            info = BitgetAccountInfo(
                total_balance=float(data.get("totalBalance", 0)),
                available_balance=float(data.get("availableBalance", 0)),
                unrealized_pnl=float(data.get("unrealizedPL", 0)),
                margin_ratio=float(data.get("marginRatio", 0)),
                positions=positions,
            )
            self._last_account_info = info
            return info

        except Exception as exc:
            logger.error(
                "bitget_account_fetch_failed",
                extra={"extra_fields": {"error": str(exc)}},
            )
            raise BitgetUnavailableError(f"Cannot fetch Bitget account: {exc}")

    # --- order placement ------------------------------------------------
    def place_order(
        self,
        symbol: str,
        side: TradeSide,
        size: float,
        price: float,
        order_type: str = "limit",
    ) -> BitgetOrder:
        """Place a demo order on Bitget."""
        if not self.enabled:
            logger.info(
                "bitget_mock_order",
                extra={
                    "extra_fields": {
                        "symbol": symbol,
                        "side": side.value,
                        "size": size,
                        "price": price,
                    }
                },
            )
            if isinstance(self.transport, MockBitgetTransport):
                order = BitgetOrder(
                    order_id=f"mock_{int(time.time() * 1000)}",
                    symbol=symbol,
                    side=side.value,
                    size=size,
                    price=price,
                    order_type=order_type,
                    status="filled",
                )
                self.transport.orders.append(order)
                return order
            raise BitgetUnavailableError("Bitget is not configured")

        bitget_side = "buy" if side == TradeSide.BUY else "sell"

        # Map Eventra symbols to Bitget symbols
        bitget_symbol = self._map_symbol(symbol)
        if bitget_symbol is None:
            logger.info(
                "bitget_skip_non_crypto",
                extra={"extra_fields": {"symbol": symbol}},
            )
            return BitgetOrder(
                order_id=f"skipped_{int(time.time() * 1000)}",
                symbol=symbol,
                side=bitget_side,
                size=size,
                price=price,
                order_type=order_type,
                status="skipped",
            )

        body = {
            "symbol": bitget_symbol,
            "side": bitget_side,
            "size": str(size),
            "price": str(price),
            "orderType": order_type,
            "tdMode": "cross",  # Cross margin mode for demo
        }

        try:
            data = self.transport.request("POST", "/api/v2/mix/order/place-order", body)
            order = BitgetOrder(
                order_id=data.get("orderId", "unknown"),
                symbol=bitget_symbol,
                side=bitget_side,
                size=size,
                price=price,
                order_type=order_type,
                status="filled",
            )
            logger.info(
                "bitget_order_placed",
                extra={
                    "extra_fields": {
                        "order_id": order.order_id,
                        "symbol": bitget_symbol,
                        "side": bitget_side,
                        "size": size,
                        "price": price,
                    }
                },
            )
            return order

        except Exception as exc:
            logger.error(
                "bitget_order_failed",
                extra={
                    "extra_fields": {
                        "symbol": bitget_symbol,
                        "side": bitget_side,
                        "error": str(exc),
                    }
                },
            )
            raise

    # Symbols that Bitget supports as USDT-margined futures.
    SUPPORTED_CRYPTO = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
        "XRP": "XRPUSDT",
        "DOGE": "DOGEUSDT",
        "ADA": "ADAUSDT",
        "AVAX": "AVAXUSDT",
        "DOT": "DOTUSDT",
        "LINK": "LINKUSDT",
        "MATIC": "MATICUSDT",
        "UNI": "UNIUSDT",
        "ATOM": "ATOMUSDT",
        "LTC": "LTCUSDT",
    }

    def _map_symbol(self, symbol: str) -> Optional[str]:
        """Map Eventra symbol to Bitget symbol format.

        Returns None for assets Bitget does not support (stocks, ETFs).
        """
        if symbol in self.SUPPORTED_CRYPTO:
            return self.SUPPORTED_CRYPTO[symbol]

        # Non-crypto assets (stocks, ETFs) are not supported on Bitget
        logger.info(
            "bitget_symbol_not_supported",
            extra={"extra_fields": {"symbol": symbol}},
        )
        return None

    # --- status ---------------------------------------------------------
    def is_configured(self) -> bool:
        """Check if Bitget is properly configured."""
        return self.enabled

    def health_check(self) -> Dict[str, Any]:
        """Check Bitget connection health."""
        if not self.enabled:
            return {
                "status": "not_configured",
                "message": "Bitget API keys not set. Using mock transport.",
                "demo_mode": True,
            }

        try:
            info = self.get_account_info()
            return {
                "status": "connected",
                "total_balance": info.total_balance,
                "available_balance": info.available_balance,
                "positions_count": len(info.positions),
                "demo_mode": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": str(exc),
                "demo_mode": True,
            }
