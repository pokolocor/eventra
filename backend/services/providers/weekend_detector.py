"""Weekend event detector - identifies events that occur when traditional markets are closed.

This is crucial for the 7x24 trading theme since crypto/rToken markets continue trading
on weekends while traditional markets are closed, creating unique opportunities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class WeekendEventDetector:
    """Detect and analyze events that occur during market closures."""

    # Market hours (Eastern Time)
    MARKET_OPEN_HOUR = 9  # 9:30 AM ET
    MARKET_OPEN_MINUTE = 30
    MARKET_CLOSE_HOUR = 16  # 4:00 PM ET
    MARKET_CLOSE_MINUTE = 0

    def __init__(self) -> None:
        pass

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """Check if US stock market is currently open.

        Args:
            dt: Datetime to check (defaults to now in UTC)

        Returns:
            True if market is open, False otherwise.
        """
        if dt is None:
            dt = datetime.now(timezone.utc)

        # Convert to Eastern Time (UTC-5 or UTC-4 depending on DST)
        # Simplified: assume UTC-5 (EST)
        et_hour = (dt.hour - 5) % 24
        weekday = dt.weekday()  # 0 = Monday, 6 = Sunday

        # Weekend check
        if weekday >= 5:  # Saturday or Sunday
            return False

        # Time check
        market_open_minutes = self.MARKET_OPEN_HOUR * 60 + self.MARKET_OPEN_MINUTE
        market_close_minutes = self.MARKET_CLOSE_HOUR * 60 + self.MARKET_CLOSE_MINUTE
        current_minutes = et_hour * 60 + dt.minute

        return market_open_minutes <= current_minutes < market_close_minutes

    def is_weekend(self, dt: Optional[datetime] = None) -> bool:
        """Check if it's currently a weekend."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        return dt.weekday() >= 5

    def is_after_hours(self, dt: Optional[datetime] = None) -> bool:
        """Check if it's after market hours on a weekday."""
        if dt is None:
            dt = datetime.now(timezone.utc)

        if self.is_weekend(dt):
            return False

        et_hour = (dt.hour - 5) % 24
        current_minutes = et_hour * 60 + dt.minute
        market_close_minutes = self.MARKET_CLOSE_HOUR * 60 + self.MARKET_CLOSE_MINUTE

        return current_minutes >= market_close_minutes

    def analyze_weekend_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze an event that occurred during market closure.

        Args:
            event: Event dict with timestamp, title, category, etc.

        Returns:
            Analysis dict with weekend impact assessment.
        """
        timestamp_str = event.get("timestamp")
        if timestamp_str:
            try:
                event_time = datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                event_time = datetime.now(timezone.utc)
        else:
            event_time = datetime.now(timezone.utc)

        is_weekend_event = self.is_weekend(event_time)
        is_after_hours_event = self.is_after_hours(event_time)

        # Determine impact multiplier for weekend/after-hours events
        # These events can cause gaps when markets reopen
        impact_multiplier = 1.0
        gap_risk = "low"

        if is_weekend_event:
            impact_multiplier = 1.5  # Weekend events have higher impact
            gap_risk = "high"
        elif is_after_hours_event:
            impact_multiplier = 1.2
            gap_risk = "medium"

        # Assess affected assets
        affected_assets = event.get("affected_assets", [])

        # Generate weekend-specific analysis
        analysis = {
            "event_time": event_time.isoformat(),
            "is_weekend": is_weekend_event,
            "is_after_hours": is_after_hours_event,
            "market_status": self._get_market_status(event_time),
            "impact_multiplier": impact_multiplier,
            "gap_risk": gap_risk,
            "affected_assets": affected_assets,
            "recommendation": self._generate_recommendation(
                event, is_weekend_event, is_after_hours_event
            ),
            "rToken_opportunity": self._assess_rtoken_opportunity(
                event, is_weekend_event
            ),
        }

        return analysis

    def _get_market_status(self, dt: datetime) -> str:
        """Get human-readable market status."""
        if self.is_weekend(dt):
            return "CLOSED (Weekend)"
        elif self.is_after_hours(dt):
            return "CLOSED (After Hours)"
        elif self.is_market_open(dt):
            return "OPEN"
        else:
            return "CLOSED (Pre-Market)"

    def _generate_recommendation(
        self, event: Dict[str, Any], is_weekend: bool, is_after_hours: bool
    ) -> str:
        """Generate trading recommendation based on event timing."""
        importance = event.get("importance", "medium")
        category = event.get("category", "other")

        if is_weekend:
            if importance in ["critical", "high"]:
                return (
                    f"High-impact event during weekend closure. rToken markets are reacting now, "
                    f"but expect significant gaps when US markets reopen Monday. "
                    f"Consider hedging via rTokens or waiting for Monday's open to assess full impact."
                )
            else:
                return (
                    f"Event occurred during weekend. Monitor rToken price action for early signals, "
                    f"but wait for traditional market open to confirm direction."
                )
        elif is_after_hours:
            if importance in ["critical", "high"]:
                return (
                    f"After-hours event with high impact potential. Expect gap up/down at tomorrow's open. "
                    f"rTokens may provide early exposure if you need to position before market open."
                )
            else:
                return (
                    f"After-hours event. Monitor pre-market futures for direction, "
                    f"but impact may be limited at regular open."
                )
        else:
            return "Event during market hours. Standard trading protocols apply."

    def _assess_rtoken_opportunity(
        self, event: Dict[str, Any], is_weekend: bool
    ) -> Dict[str, Any]:
        """Assess rToken-specific opportunity from this event."""
        if not is_weekend:
            return {"opportunity": "none", "reason": "Event during market hours"}

        importance = event.get("importance", "medium")
        affected_assets = event.get("affected_assets", [])

        # Check if any affected assets have rToken equivalents
        rtoken_eligible = [
            a
            for a in affected_assets
            if a in ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "BTC", "ETH"]
        ]

        if not rtoken_eligible:
            return {
                "opportunity": "none",
                "reason": "No rToken-eligible assets affected",
            }

        if importance in ["critical", "high"]:
            return {
                "opportunity": "high",
                "reason": (
                    f"Weekend event affecting {', '.join(rtoken_eligible)}. "
                    f"rTokens provide immediate exposure while traditional markets are closed. "
                    f"Expect premium to converge at Monday's open."
                ),
                "eligible_rtokens": [f"r{asset}" for asset in rtoken_eligible],
            }
        else:
            return {
                "opportunity": "medium",
                "reason": f"Weekend event with moderate impact on {', '.join(rtoken_eligible)}.",
                "eligible_rtokens": [f"r{asset}" for asset in rtoken_eligible],
            }

    def generate_weekend_alert(
        self, events: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Generate a weekend alert event if significant events occurred during market closure.

        Args:
            events: List of recent events

        Returns:
            Alert event dict if significant weekend activity, None otherwise.
        """
        weekend_events = []

        for event in events:
            analysis = self.analyze_weekend_event(event)
            if analysis["is_weekend"] and event.get("importance") in [
                "critical",
                "high",
            ]:
                weekend_events.append(
                    {
                        "event": event,
                        "analysis": analysis,
                    }
                )

        if not weekend_events:
            return None

        # Generate summary alert
        titles = [e["event"]["title"] for e in weekend_events[:3]]
        affected = set()
        for e in weekend_events:
            affected.update(e["event"].get("affected_assets", []))

        title = f"Weekend Alert: {len(weekend_events)} high-impact event(s) during market closure"
        summary = (
            f"Significant events occurred while US markets are closed: {'; '.join(titles)}. "
            f"Affected assets: {', '.join(list(affected)[:5])}. "
            f"Expect volatility and potential gaps when markets reopen. "
            f"rToken markets are providing early price discovery."
        )

        return {
            "title": title,
            "source": "Eventra Weekend Detector",
            "category": "weekend_alert",
            "importance": "high",
            "summary": summary,
            "affected_assets": list(affected)[:5],
            "raw": {
                "provider": "weekend_detector",
                "weekend_events": weekend_events,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
