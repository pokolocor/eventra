"""Market data provider abstraction + deterministic demo implementation.

Swap `DemoMarketDataProvider` for a real vendor by implementing
`MarketDataProvider` and changing one line in `backend/services/registry.py`.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    asset_class: str
    base_price: float
    annualized_vol: float
    avg_daily_volume_usd: float
    sector: str = ""

    @property
    def daily_vol(self) -> float:
        return self.annualized_vol / math.sqrt(252)


UNIVERSE: Dict[str, Instrument] = {
    i.symbol: i
    for i in [
        Instrument("SPY", "SPDR S&P 500 ETF", "equity_etf", 572.40, 0.14, 32_000_000_000, "broad_market"),
        Instrument("QQQ", "Invesco QQQ Trust", "equity_etf", 498.15, 0.19, 21_000_000_000, "technology"),
        Instrument("IWM", "iShares Russell 2000 ETF", "equity_etf", 224.80, 0.21, 3_400_000_000, "small_cap"),
        Instrument("NVDA", "NVIDIA Corporation", "equity", 142.60, 0.46, 28_000_000_000, "semiconductors"),
        Instrument("SOXX", "iShares Semiconductor ETF", "equity_etf", 232.10, 0.31, 1_900_000_000, "semiconductors"),
        Instrument("AAPL", "Apple Inc.", "equity", 236.40, 0.24, 9_800_000_000, "technology"),
        Instrument("MSFT", "Microsoft Corporation", "equity", 448.20, 0.22, 8_100_000_000, "technology"),
        Instrument("JPM", "JPMorgan Chase & Co.", "equity", 232.90, 0.23, 2_600_000_000, "financials"),
        Instrument("XLE", "Energy Select Sector SPDR", "equity_etf", 92.35, 0.26, 1_300_000_000, "energy"),
        Instrument("USO", "United States Oil Fund", "commodity_etf", 74.10, 0.42, 900_000_000, "energy"),
        Instrument("GLD", "SPDR Gold Shares", "commodity_etf", 268.75, 0.15, 1_600_000_000, "metals"),
        Instrument("TLT", "iShares 20+ Year Treasury Bond ETF", "fixed_income_etf", 89.40, 0.17, 2_900_000_000, "rates"),
        Instrument("EEM", "iShares MSCI Emerging Markets ETF", "equity_etf", 45.60, 0.20, 1_500_000_000, "international"),
        Instrument("BTC", "Bitcoin", "crypto", 67_450.00, 0.62, 24_000_000_000, "digital_assets"),
        Instrument("ETH", "Ethereum", "crypto", 3_480.00, 0.74, 12_500_000_000, "digital_assets"),
        Instrument("ILLIQ", "Illiquid Micro Cap Demo", "equity", 4.20, 1.35, 900_000, "speculative"),
    ]
}


@dataclass
class Quote:
    symbol: str
    price: float
    change_pct: float
    annualized_vol: float
    avg_daily_volume_usd: float
    name: str
    asset_class: str
    sector: str
    as_of_tick: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class,
            "sector": self.sector,
            "price": round(self.price, 4),
            "change_pct": round(self.change_pct, 4),
            "annualized_vol": round(self.annualized_vol, 4),
            "avg_daily_volume_usd": self.avg_daily_volume_usd,
            "as_of_tick": self.as_of_tick,
        }


class MarketDataProvider(ABC):
    """Interface a real market data vendor must implement."""

    @abstractmethod
    def quote(self, symbol: str) -> Optional[Quote]:
        ...

    @abstractmethod
    def history(self, symbol: str, points: int = 40) -> List[Dict[str, float]]:
        ...

    @abstractmethod
    def advance_tick(self, shocks: Optional[Dict[str, float]] = None) -> int:
        ...

    def liquidity(self, symbol: str) -> float:
        quote = self.quote(symbol)
        return quote.avg_daily_volume_usd if quote else 0.0

    def volatility(self, symbol: str) -> float:
        quote = self.quote(symbol)
        return quote.annualized_vol if quote else 1.0


def _noise(seed: str) -> float:
    """Deterministic pseudo-random value in [-1, 1] for a seed string."""

    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return (value - 0.5) * 2.0


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic, reproducible simulated market.

    Prices follow a seeded random walk so the demo looks alive but is identical
    across restarts - important for a judged hackathon demo. Optional `shocks`
    let the agent pipeline move prices after an event is processed.
    """

    def __init__(self, universe: Optional[Dict[str, Instrument]] = None, seed: str = "eventra") -> None:
        self.universe = universe or UNIVERSE
        self.seed = seed
        self.tick = 0
        self._shock_by_symbol: Dict[str, float] = {}
        self._shock_tick: Dict[str, int] = {}

    # --- internals ------------------------------------------------------
    def _path(self, symbol: str, upto_tick: int) -> List[float]:
        instrument = self.universe[symbol]
        price = instrument.base_price
        path = [price]
        for step in range(1, upto_tick + 1):
            drift = 0.0004
            shock = 0.0
            if symbol in self._shock_tick and self._shock_tick[symbol] == step:
                shock = self._shock_by_symbol.get(symbol, 0.0)
            wiggle = _noise(f"{self.seed}:{symbol}:{step}") * instrument.daily_vol * 0.55
            price = max(0.01, price * (1.0 + drift + wiggle + shock))
            path.append(price)
        return path

    def _price_at(self, symbol: str, tick: int) -> float:
        return self._path(symbol, max(0, tick))[-1]

    # --- public API -----------------------------------------------------
    def advance_tick(self, shocks: Optional[Dict[str, float]] = None) -> int:
        self.tick += 1
        if shocks:
            for symbol, magnitude in shocks.items():
                key = symbol.upper()
                if key in self.universe:
                    self._shock_by_symbol[key] = float(magnitude)
                    self._shock_tick[key] = self.tick
        return self.tick

    def quote(self, symbol: str) -> Optional[Quote]:
        key = symbol.upper()
        instrument = self.universe.get(key)
        if instrument is None:
            return None
        price = self._price_at(key, self.tick)
        previous = self._price_at(key, max(0, self.tick - 1))
        change_pct = ((price / previous) - 1.0) * 100.0 if previous else 0.0
        return Quote(
            symbol=key,
            price=price,
            change_pct=change_pct,
            annualized_vol=instrument.annualized_vol,
            avg_daily_volume_usd=instrument.avg_daily_volume_usd,
            name=instrument.name,
            asset_class=instrument.asset_class,
            sector=instrument.sector,
            as_of_tick=self.tick,
        )

    def history(self, symbol: str, points: int = 40) -> List[Dict[str, float]]:
        key = symbol.upper()
        if key not in self.universe:
            return []
        start = max(0, self.tick - points + 1)
        path = self._path(key, self.tick)
        return [{"tick": float(i), "price": round(path[i], 4)} for i in range(start, len(path))]

    def all_quotes(self) -> List[Quote]:
        return [q for q in (self.quote(s) for s in self.universe) if q is not None]
