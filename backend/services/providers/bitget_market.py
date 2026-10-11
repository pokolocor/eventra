"""Bitget live market data provider - fetches real-time prices and funding rates."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BitgetMarketData:
    """Fetch live market data from Bitget public API (no auth required)."""

    BASE_URL = "https://api.bitget.com"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current ticker for a symbol (e.g., BTCUSDT)."""
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/tickers?symbol={symbol}"
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "00000" and data.get("data"):
                    return (
                        data["data"][0]
                        if isinstance(data["data"], list)
                        else data["data"]
                    )
                else:
                    logger.warning(
                        f"Bitget API error for {symbol}: {data.get('msg', 'Unknown error')}"
                    )
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
        return None

    def get_all_tickers(self) -> List[Dict[str, Any]]:
        """Get all spot market tickers."""
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/tickers"
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "00000" and data.get("data"):
                    return data["data"]
        except Exception as e:
            logger.error(f"Failed to fetch all tickers: {e}")
        return []

    def get_funding_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current funding rate for a futures symbol (e.g., BTCUSDT)."""
        try:
            url = f"{self.BASE_URL}/api/v2/mix/market/current-fund-rate?symbol={symbol}&productType=USDT-FUTURES"
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "00000" and data.get("data"):
                    return (
                        data["data"][0]
                        if isinstance(data["data"], list)
                        else data["data"]
                    )
                else:
                    logger.warning(
                        f"Bitget funding rate error for {symbol}: {data.get('msg', 'Unknown error')}"
                    )
        except Exception as e:
            logger.error(f"Failed to fetch funding rate for {symbol}: {e}")
        return None

    def get_orderbook(self, symbol: str, limit: int = 15) -> Optional[Dict[str, Any]]:
        """Get orderbook depth."""
        try:
            url = f"{self.BASE_URL}/api/spot/v1/market/depth?symbol={symbol}&limit={limit}"
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("code") == "00000" and data.get("data"):
                    return data["data"]
        except Exception:
            pass
        return None

    def get_crypto_prices(
        self, symbols: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get current prices for crypto symbols.

        Args:
            symbols: List of symbols like ["BTC", "ETH", "SOL"]. If None, returns major pairs.

        Returns:
            Dict mapping symbol to price data.
        """
        if symbols is None:
            symbols = [
                "BTC",
                "ETH",
                "SOL",
                "BNB",
                "XRP",
                "DOGE",
                "ADA",
                "AVAX",
                "DOT",
                "MATIC",
            ]

        # Use batch endpoint for efficiency
        all_tickers = self.get_all_tickers()
        if not all_tickers:
            # Fallback to individual calls if batch fails
            logger.warning(
                "Batch ticker fetch failed, falling back to individual calls"
            )
            return self._get_crypto_prices_individual(symbols)

        # Build symbol lookup map
        ticker_map = {}
        for ticker in all_tickers:
            symbol_name = ticker.get("symbol", "")
            if symbol_name.endswith("USDT"):
                base = symbol_name[:-4]
                ticker_map[base] = ticker

        prices = {}
        for symbol in symbols:
            ticker = ticker_map.get(symbol)
            if ticker:
                prices[symbol] = {
                    "price": float(ticker.get("lastPr", 0)),
                    "bid": float(ticker.get("bidPr", 0)),
                    "ask": float(ticker.get("askPr", 0)),
                    "volume_24h": float(ticker.get("baseVolume", 0)),
                    "quote_volume_24h": float(ticker.get("quoteVolume", 0)),
                    "change_24h": float(ticker.get("change24h", 0)),
                    "high_24h": float(ticker.get("high24h", 0)),
                    "low_24h": float(ticker.get("low24h", 0)),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        return prices

    def _get_crypto_prices_individual(
        self, symbols: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Fallback: fetch prices one by one."""
        prices = {}
        for symbol in symbols:
            ticker = self.get_ticker(f"{symbol}USDT")
            if ticker:
                prices[symbol] = {
                    "price": float(ticker.get("lastPr", 0)),
                    "bid": float(ticker.get("bidPr", 0)),
                    "ask": float(ticker.get("askPr", 0)),
                    "volume_24h": float(ticker.get("baseVolume", 0)),
                    "quote_volume_24h": float(ticker.get("quoteVolume", 0)),
                    "change_24h": float(ticker.get("change24h", 0)),
                    "high_24h": float(ticker.get("high24h", 0)),
                    "low_24h": float(ticker.get("low24h", 0)),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        return prices

    def get_funding_rates(
        self, symbols: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get current funding rates for futures symbols.

        Args:
            symbols: List of symbols like ["BTC", "ETH", "SOL"]. If None, returns major pairs.

        Returns:
            Dict mapping symbol to funding rate data.
        """
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "BNB", "XRP"]

        rates = {}
        for symbol in symbols:
            funding = self.get_funding_rate(f"{symbol}USDT")
            if funding:
                rates[symbol] = {
                    "funding_rate": float(funding.get("fundingRate", 0)),
                    "funding_time": funding.get("fundingTime"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        return rates

    def get_market_summary(self) -> Dict[str, Any]:
        """Get comprehensive market summary with prices and funding rates."""
        prices = self.get_crypto_prices()
        funding = self.get_funding_rates()

        return {
            "prices": prices,
            "funding_rates": funding,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "bitget_live",
        }
