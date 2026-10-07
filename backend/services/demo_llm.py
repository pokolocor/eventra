"""Demo Mode LLM.

This module is deliberately isolated from `qwen_service.py`. It exists so the
whole Eventra pipeline can be demonstrated with zero external dependencies -
no API key, no network. It is only used when `QWEN_API_KEY` is absent or when
`EVENTRA_DEMO_MODE=1` forces it.

Everything it returns is labelled `provider="demo-mock"` and the UI prints a
`PAPER / DEMO` banner, so a demo audience can never confuse it with real Qwen
output.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from backend.models.domain import Event, QwenAnalysis
from backend.services.providers.event_templates import EVENT_TEMPLATES

_KEYWORD_RULES: List[Dict[str, Any]] = [
    {
        "match": ["fed", "fomc", "rate cut", "rates unchanged", "powell", "hawkish"],
        "event_type": "monetary_policy",
        "sentiment": "bearish",
        "market_regime": "risk_off",
        "recommended_action": "reduce_risk",
        "confidence": 0.74,
        "time_horizon": "1-5 days",
        "positive": ["JPM"],
        "negative": ["QQQ", "TLT", "IWM", "BTC"],
    },
    {
        "match": ["cpi", "inflation", "pce", "disinflation", "consumer prices"],
        "event_type": "inflation",
        "sentiment": "bullish",
        "market_regime": "risk_on",
        "recommended_action": "increase_risk",
        "confidence": 0.71,
        "time_horizon": "1-5 days",
        "positive": ["QQQ", "TLT", "SPY", "IWM"],
        "negative": ["XLE"],
    },
    {
        "match": ["beat", "beats", "raises guidance", "record revenue", "above expectations"],
        "event_type": "earnings",
        "sentiment": "bullish",
        "market_regime": "risk_on",
        "recommended_action": "increase_risk",
        "confidence": 0.78,
        "time_horizon": "1-5 days",
        "positive": [],
        "negative": [],
    },
    {
        "match": ["miss", "misses", "cuts guidance", "below expectations", "warns"],
        "event_type": "earnings",
        "sentiment": "bearish",
        "market_regime": "risk_off",
        "recommended_action": "reduce_risk",
        "confidence": 0.76,
        "time_horizon": "1-5 days",
        "positive": [],
        "negative": [],
    },
    {
        "match": ["oil", "opec", "brent", "crude", "natural gas", "energy"],
        "event_type": "commodity",
        "sentiment": "mixed",
        "market_regime": "risk_off",
        "recommended_action": "rotate",
        "confidence": 0.68,
        "time_horizon": "1-4 weeks",
        "positive": ["XLE", "USO", "GLD"],
        "negative": ["QQQ", "TLT", "SPY"],
    },
    {
        "match": ["war", "strike", "escalation", "hormuz", "sanctions", "conflict", "vix"],
        "event_type": "geopolitical",
        "sentiment": "bearish",
        "market_regime": "risk_off",
        "recommended_action": "hedge",
        "confidence": 0.72,
        "time_horizon": "1-5 days",
        "positive": ["GLD", "TLT", "USO"],
        "negative": ["QQQ", "SPY", "BTC", "IWM"],
    },
    {
        "match": ["bitcoin", "ethereum", "crypto", "etf", "sec", "stablecoin", "token"],
        "event_type": "crypto_regulation",
        "sentiment": "bullish",
        "market_regime": "risk_on",
        "recommended_action": "increase_risk",
        "confidence": 0.69,
        "time_horizon": "1-4 weeks",
        "positive": ["BTC", "ETH"],
        "negative": [],
    },
    {
        "match": ["payroll", "jobless", "unemployment", "employment", "wage"],
        "event_type": "employment",
        "sentiment": "bearish",
        "market_regime": "risk_off",
        "recommended_action": "reduce_risk",
        "confidence": 0.66,
        "time_horizon": "1-5 days",
        "positive": ["JPM"],
        "negative": ["TLT", "QQQ", "IWM"],
    },
    {
        "match": ["gdp", "growth", "consumer spending", "purchases"],
        "event_type": "growth",
        "sentiment": "mixed",
        "market_regime": "risk_on",
        "recommended_action": "rotate",
        "confidence": 0.64,
        "time_horizon": "1-4 weeks",
        "positive": ["SPY", "IWM", "JPM"],
        "negative": ["TLT"],
    },
]

_DEFAULT_RULE: Dict[str, Any] = {
    "event_type": "macro",
    "sentiment": "neutral",
    "market_regime": "neutral",
    "recommended_action": "hold",
    "confidence": 0.55,
    "time_horizon": "1-5 days",
    "positive": ["SPY"],
    "negative": [],
}


class DemoLLMService:
    """Drop-in stand-in for `QwenService` with the same `analyze_event` shape."""

    provider = "demo-mock"
    model = "eventra-demo-v1"

    def __init__(self, latency_ms: int = 0) -> None:
        self.latency_ms = latency_ms

    @property
    def available(self) -> bool:
        return True

    def analyze_event(self, event: Event) -> QwenAnalysis:
        started = time.perf_counter()
        payload = self._payload_for(event)
        analysis = QwenAnalysis.model_validate(payload)
        analysis.provider = self.provider
        analysis.model = self.model
        analysis.attempts = 1
        analysis.latency_ms = self.latency_ms or max(1, int((time.perf_counter() - started) * 1000))
        analysis.raw_output = (
            f"[DEMO MODE] deterministic mock interpretation for event '{event.id}'. "
            "Configure QWEN_API_KEY to use the real Qwen model."
        )
        return analysis

    # --- internals ------------------------------------------------------
    def _payload_for(self, event: Event) -> Dict[str, Any]:
        template = EVENT_TEMPLATES.get(event.template_key or "")
        if template is not None and template.expected_analysis:
            expected = template.expected_analysis
            return {
                "event_type": expected["event_type"],
                "sentiment": expected["sentiment"],
                "market_regime": expected["market_regime"],
                "confidence": expected["confidence"],
                "time_horizon": expected["time_horizon"],
                "recommended_action": expected["recommended_action"],
                "reasoning_summary": expected["reasoning_summary"],
                "affected_assets": [
                    {"symbol": s, "direction": d, "impact_score": i} for s, d, i in expected["impacts"]
                ],
                "portfolio_actions": [
                    {"symbol": s, "action": a, "percentage": p} for s, a, p in expected["actions"]
                ],
            }
        return self._heuristic_payload(event)

    def _heuristic_payload(self, event: Event) -> Dict[str, Any]:
        text = f"{event.title} {event.summary}".lower()
        rule: Optional[Dict[str, Any]] = None
        best_hits = 0
        for candidate in _KEYWORD_RULES:
            hits = sum(1 for token in candidate["match"] if token in text)
            if hits > best_hits:
                best_hits = hits
                rule = candidate
        if rule is None:
            rule = _DEFAULT_RULE

        positives = list(rule["positive"])
        negatives = list(rule["negative"])
        for symbol in event.affected_assets:
            if symbol in positives or symbol in negatives:
                continue
            (positives if rule["sentiment"] == "bullish" else negatives).append(symbol)
        positives = positives[:5]
        negatives = negatives[:5]

        base_impact = 55 + int(event.importance.value == "critical") * 18 + int(
            event.importance.value == "high"
        ) * 10
        affected: List[Dict[str, Any]] = []
        for index, symbol in enumerate(positives):
            affected.append(
                {"symbol": symbol, "direction": "positive", "impact_score": max(20, min(96, base_impact + 12 - index * 5))}
            )
        for index, symbol in enumerate(negatives):
            affected.append(
                {"symbol": symbol, "direction": "negative", "impact_score": max(20, min(96, base_impact + 8 - index * 5))}
            )
        if not affected:
            affected = [{"symbol": "SPY", "direction": "neutral", "impact_score": 35}]

        actions: List[Dict[str, Any]] = []
        intent = rule["recommended_action"]
        for symbol in positives[:3]:
            if intent == "hold":
                continue
            actions.append(
                {"symbol": symbol, "action": "INCREASE", "percentage": 6 if intent != "hedge" else 4}
            )
        for symbol in negatives[:3]:
            actions.append({"symbol": symbol, "action": "REDUCE", "percentage": 7 if intent != "hedge" else 9})
        if intent == "hedge":
            actions.append({"symbol": "GLD", "action": "INCREASE", "percentage": 6})
        if not actions:
            actions = [{"symbol": affected[0]["symbol"], "action": "HOLD", "percentage": 0}]

        return {
            "event_type": rule["event_type"],
            "sentiment": rule["sentiment"],
            "market_regime": rule["market_regime"],
            "confidence": rule["confidence"],
            "time_horizon": rule["time_horizon"],
            "recommended_action": rule["recommended_action"],
            "reasoning_summary": (
                f"Demo Mode heuristic classified '{event.title[:70]}' as {rule['event_type']} with a "
                f"{rule['sentiment']} read and a {rule['market_regime'].replace('_', '-')} regime. "
                "Configure QWEN_API_KEY for a real model interpretation."
            ),
            "affected_assets": affected,
            "portfolio_actions": actions,
        }
