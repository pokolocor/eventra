"""rToken arbitrage detector - finds price discrepancies between tokenized and real assets.

This is a key feature for the Bitget hackathon since it focuses on 7x24 trading
of tokenized US stocks (rTokens) that trade on weekends when traditional markets are closed.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RTokenArbitrageDetector:
    """Detect arbitrage opportunities between rTokens and underlying assets."""

    # Mapping of rToken symbols to their underlying assets
    RTOKEN_MAP = {
        "rSPY": "SPY",
        "rQQQ": "QQQ",
        "rAAPL": "AAPL",
        "rMSFT": "MSFT",
        "rGOOGL": "GOOGL",
        "rAMZN": "AMZN",
        "rTSLA": "TSLA",
        "rNVDA": "NVDA",
        "rMETA": "META",
        "rBTC": "BTC",
        "rETH": "ETH",
    }

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def detect_arbitrage(
        self,
        rtoken_prices: Dict[str, float],
        underlying_prices: Dict[str, float],
        threshold_pct: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Detect arbitrage opportunities between rTokens and underlying assets.

        Args:
            rtoken_prices: Dict mapping rToken symbol to price (e.g., {"rSPY": 582.40})
            underlying_prices: Dict mapping underlying symbol to price (e.g., {"SPY": 577.60})
            threshold_pct: Minimum premium/discount percentage to flag as opportunity

        Returns:
            List of arbitrage opportunities with direction and magnitude.
        """
        opportunities = []

        for rtoken, underlying in self.RTOKEN_MAP.items():
            if rtoken not in rtoken_prices or underlying not in underlying_prices:
                continue

            rtoken_price = rtoken_prices[rtoken]
            underlying_price = underlying_prices[underlying]

            if underlying_price == 0:
                continue

            # Calculate premium/discount
            premium_pct = ((rtoken_price - underlying_price) / underlying_price) * 100

            if abs(premium_pct) >= threshold_pct:
                # Determine arbitrage direction
                if premium_pct > 0:
                    # rToken trading at premium - sell rToken, buy underlying
                    direction = "sell_rtoken_buy_underlying"
                    action = f"Short {rtoken}, Long {underlying}"
                else:
                    # rToken trading at discount - buy rToken, sell underlying
                    direction = "buy_rtoken_sell_underlying"
                    action = f"Long {rtoken}, Short {underlying}"

                opportunities.append(
                    {
                        "rtoken": rtoken,
                        "underlying": underlying,
                        "rtoken_price": rtoken_price,
                        "underlying_price": underlying_price,
                        "premium_pct": round(premium_pct, 3),
                        "direction": direction,
                        "action": action,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        # Sort by absolute premium (largest opportunities first)
        opportunities.sort(key=lambda x: abs(x["premium_pct"]), reverse=True)
        return opportunities

    def generate_arbitrage_event(
        self, opportunities: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Generate an event from arbitrage opportunities.

        Args:
            opportunities: List of arbitrage opportunities from detect_arbitrage()

        Returns:
            Event dict if significant arbitrage found, None otherwise.
        """
        if not opportunities:
            return None

        # Take the largest opportunity
        opp = opportunities[0]

        # Determine importance based on premium size
        premium = abs(opp["premium_pct"])
        if premium >= 2.0:
            importance = "critical"
        elif premium >= 1.0:
            importance = "high"
        elif premium >= 0.5:
            importance = "medium"
        else:
            importance = "low"

        title = f"rToken arbitrage: {opp['rtoken']} trading at {opp['premium_pct']:+.2f}% {'premium' if opp['premium_pct'] > 0 else 'discount'} to {opp['underlying']}"

        summary = (
            f"{opp['rtoken']} is trading at ${opp['rtoken_price']:.2f} while {opp['underlying']} "
            f"is at ${opp['underlying_price']:.2f}, creating a {opp['premium_pct']:+.2f}% spread. "
            f"Recommended action: {opp['action']}. "
            f"This arbitrage opportunity exists because rTokens trade 7x24 while traditional markets have limited hours."
        )

        return {
            "title": title,
            "source": "Eventra Arbitrage Detector",
            "category": "arbitrage",
            "importance": importance,
            "summary": summary,
            "affected_assets": [opp["rtoken"], opp["underlying"]],
            "raw": {
                "provider": "rtoken_arbitrage",
                "opportunities": opportunities,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def check_weekend_premium(
        self, rtoken_prices: Dict[str, float], underlying_prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """Check for weekend premium/discount patterns.

        On weekends, rTokens often trade at a premium because they provide exposure
        to US equities when traditional markets are closed.

        Returns analysis of weekend premium patterns.
        """
        now = datetime.now(timezone.utc)
        is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6

        opportunities = self.detect_arbitrage(
            rtoken_prices, underlying_prices, threshold_pct=0.3
        )

        return {
            "is_weekend": is_weekend,
            "day_of_week": now.strftime("%A"),
            "opportunities_count": len(opportunities),
            "opportunities": opportunities,
            "analysis": self._analyze_weekend_pattern(opportunities, is_weekend),
            "timestamp": now.isoformat(),
        }

    def _analyze_weekend_pattern(
        self, opportunities: List[Dict[str, Any]], is_weekend: bool
    ) -> str:
        """Analyze weekend premium patterns."""
        if not opportunities:
            return "No significant rToken arbitrage opportunities detected."

        avg_premium = sum(abs(opp["premium_pct"]) for opp in opportunities) / len(
            opportunities
        )

        if is_weekend:
            if avg_premium > 1.0:
                return (
                    f"Weekend premium detected: rTokens trading at {avg_premium:.2f}% average premium. "
                    f"This is typical as rTokens provide 7x24 exposure to US equities while traditional markets are closed. "
                    f"Consider shorting rTokens if you expect the premium to converge at Monday's open."
                )
            else:
                return (
                    f"Moderate weekend spread: {avg_premium:.2f}% average. "
                    f"Arbitrage opportunities exist but may not cover transaction costs."
                )
        else:
            if avg_premium > 0.5:
                return (
                    f"Unexpected weekday arbitrage: {avg_premium:.2f}% average premium. "
                    f"This may indicate liquidity issues or delayed price discovery in rToken markets."
                )
            else:
                return (
                    f"Normal weekday pricing: {avg_premium:.2f}% average spread. "
                    f"rTokens are tracking underlying assets closely during market hours."
                )
