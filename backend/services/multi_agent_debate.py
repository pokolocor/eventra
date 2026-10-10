"""Multi-agent debate system - bull vs bear analysis before final decision.

This implements a sophisticated AI pattern where two agents with different perspectives
debate an event before reaching a consensus. This reduces bias and improves decision quality.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from backend.config import Settings, settings as default_settings
from backend.models.domain import Event, QwenAnalysis
from backend.services.qwen_service import QwenService, extract_json, QwenServiceError


BULL_PROMPT = """You are a BULLISH analyst. Your job is to find POSITIVE aspects of this event.

Focus on:
- Upside potential and opportunities
- Why this could be good for markets
- Sectors/assets that benefit
- Reasons to be optimistic

Be constructive but realistic. Return JSON only.

Schema:
{
  "sentiment": "bullish",
  "confidence": 0.0-1.0,
  "bull_case": "2-3 sentence argument for why this is positive",
  "benefiting_assets": [{"symbol":"TICKER","reason":"why it benefits","impact_score":0-100}],
  "recommended_action": "increase_risk|hold",
  "time_horizon": "intraday|1-5 days|1-4 weeks|1-6 months"
}"""

BEAR_PROMPT = """You are a BEARISH analyst. Your job is to find NEGATIVE aspects of this event.

Focus on:
- Downside risks and threats
- Why this could hurt markets
- Sectors/assets that suffer
- Reasons to be cautious

Be constructive but realistic. Return JSON only.

Schema:
{
  "sentiment": "bearish",
  "confidence": 0.0-1.0,
  "bear_case": "2-3 sentence argument for why this is negative",
  "at_risk_assets": [{"symbol":"TICKER","reason":"why it's at risk","impact_score":0-100}],
  "recommended_action": "reduce_risk|hedge",
  "time_horizon": "intraday|1-5 days|1-4 weeks|1-6 months"
}"""

JUDGE_PROMPT = """You are a PORTFOLIO MANAGER evaluating a debate between a bull and bear analyst.

BULL CASE:
{bull_case}

BEAR CASE:
{bear_case}

EVENT:
{event_summary}

Make a final decision. Consider both arguments, weigh the evidence, and provide a balanced view.

Return JSON only:
{
  "final_sentiment": "bullish|bearish|neutral|mixed",
  "confidence": 0.0-1.0,
  "market_regime": "risk_on|risk_off|neutral",
  "reasoning": "Brief explanation of your decision",
  "affected_assets": [{"symbol":"TICKER","direction":"positive|negative|neutral","impact_score":0-100}],
  "recommended_action": "increase_risk|reduce_risk|hold|hedge|rotate",
  "time_horizon": "intraday|1-5 days|1-4 weeks|1-6 months",
  "portfolio_actions": [{"symbol":"TICKER","action":"BUY|SELL|INCREASE|REDUCE|HOLD|HEDGE","percentage":0-100}]
}"""


class MultiAgentDebate:
    """Orchestrate bull vs bear debate for improved analysis."""

    def __init__(self, config: Optional[Settings] = None) -> None:
        self.config = config or default_settings
        self.qwen = QwenService(config)

    def run_debate(self, event: Event) -> Dict[str, Any]:
        """Run a full bull vs bear debate on an event.

        Returns:
            Dict with bull_case, bear_case, judge_decision, and metadata.
        """
        if not self.qwen.available:
            raise QwenServiceError("Qwen API key not configured")

        started = time.perf_counter()

        # Step 1: Get bull analysis
        bull_messages = [
            {"role": "system", "content": BULL_PROMPT},
            {"role": "user", "content": self._format_event(event)},
        ]
        bull_response = self.qwen._chat(bull_messages)
        bull_data = extract_json(bull_response)

        # Step 2: Get bear analysis
        bear_messages = [
            {"role": "system", "content": BEAR_PROMPT},
            {"role": "user", "content": self._format_event(event)},
        ]
        bear_response = self.qwen._chat(bear_messages)
        bear_data = extract_json(bear_response)

        # Step 3: Judge decides
        judge_messages = [
            {
                "role": "system",
                "content": JUDGE_PROMPT.format(
                    bull_case=json.dumps(bull_data, indent=2),
                    bear_case=json.dumps(bear_data, indent=2),
                    event_summary=self._format_event(event),
                ),
            },
            {
                "role": "user",
                "content": "Make your final decision based on the debate.",
            },
        ]
        judge_response = self.qwen._chat(judge_messages)
        judge_data = extract_json(judge_response)

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return {
            "bull_case": bull_data,
            "bear_case": bear_data,
            "judge_decision": judge_data,
            "metadata": {
                "total_latency_ms": elapsed_ms,
                "model": self.config.qwen_model,
                "event_id": event.id,
            },
        }

    def _format_event(self, event: Event) -> str:
        """Format event for debate prompts."""
        return json.dumps(
            {
                "title": event.title,
                "source": event.source,
                "category": event.category.value,
                "importance": event.importance.value,
                "summary": event.summary[:400],
                "affected_assets": event.affected_assets[:5],
            },
            default=str,
        )

    def to_analysis(self, debate_result: Dict[str, Any]) -> QwenAnalysis:
        """Convert debate result to standard QwenAnalysis format.

        This allows the debate system to plug into the existing pipeline.
        """
        judge = debate_result["judge_decision"]

        # Build affected assets
        affected_assets = []
        for asset in judge.get("affected_assets", []):
            affected_assets.append(
                {
                    "symbol": asset["symbol"],
                    "direction": asset["direction"],
                    "impact_score": asset["impact_score"],
                }
            )

        # Build portfolio actions
        portfolio_actions = []
        for action in judge.get("portfolio_actions", []):
            portfolio_actions.append(
                {
                    "symbol": action["symbol"],
                    "action": action["action"],
                    "percentage": action["percentage"],
                }
            )

        analysis = QwenAnalysis(
            event_type=judge.get("event_type", "other"),
            sentiment=judge["final_sentiment"],
            market_regime=judge["market_regime"],
            confidence=judge["confidence"],
            affected_assets=affected_assets,
            time_horizon=judge["time_horizon"],
            recommended_action=judge["recommended_action"],
            portfolio_actions=portfolio_actions,
            reasoning_summary=judge.get("reasoning", ""),
            provider="qwen_debate",
            model=self.config.qwen_model,
            latency_ms=debate_result["metadata"]["total_latency_ms"],
            attempts=3,  # 3 LLM calls: bull, bear, judge
            raw_output=json.dumps(debate_result, default=str)[:8000],
        )

        return analysis
