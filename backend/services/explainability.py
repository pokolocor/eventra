"""Human-readable explanations for every agent decision.

Judges, teammates and risk officers all need the same thing: a short, honest
sentence about *why* the portfolio changed. This module turns the structured
pipeline artefacts into that sentence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.models.domain import (
    DecisionRun,
    RiskStatus,
    TradeAction,
)

_SENTIMENT_TEXT = {
    "bullish": "bullish",
    "bearish": "bearish",
    "neutral": "neutral",
    "mixed": "two-sided",
}

_REGIME_TEXT = {
    "risk_on": "risk-on",
    "risk_off": "risk-off",
    "neutral": "neutral",
}

_ACTION_VERB = {
    TradeAction.BUY: "bought",
    TradeAction.INCREASE: "added to",
    TradeAction.REDUCE: "reduced",
    TradeAction.SELL: "exited",
    TradeAction.HEDGE: "hedged with",
    TradeAction.HOLD: "held",
}


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _trim(reason: str) -> str:
    return reason.strip().rstrip(".").strip()


def _join_reasons(reasons: Any) -> str:
    cleaned = [_trim(reason) for reason in reasons if _trim(reason)]
    return "; ".join(cleaned)


def _rejection_text(risk: Any) -> str:
    reasons = [reason for reason in (risk.reasons or []) if _trim(reason)]
    headline = next((item for item in reasons if item.startswith("Blocked by")), None)
    details = [item for item in reasons if item is not headline][:2]
    if headline:
        text = f"The risk engine REJECTED the proposal. {_trim(headline)}."
        if details:
            text = f"{text} {_join_reasons(details)}."
        return text
    if not reasons:
        return "The risk engine REJECTED the proposal: it failed the deterministic risk checks."
    return f"The risk engine REJECTED the proposal because {_join_reasons(reasons[:2])}."


def explain_decision(run: DecisionRun) -> str:
    event = run.event
    analysis = run.analysis
    risk = run.risk

    if analysis is None:
        return (
            f"Eventra detected \"{event.title}\" but could not produce an interpretation. "
            f"No portfolio action was taken. {run.error or ''}".strip()
        )

    classification = (
        f"Qwen classified the event as {analysis.event_type.replace('_', ' ')} with a "
        f"{_SENTIMENT_TEXT.get(analysis.sentiment.value, analysis.sentiment.value)} read and a "
        f"{_REGIME_TEXT.get(analysis.market_regime.value, analysis.market_regime.value)} regime at "
        f"{_pct(analysis.confidence)} confidence over a {analysis.time_horizon.value} horizon."
    )

    if risk is None:
        return f"{classification} The signal never reached the risk engine, so nothing was executed."

    if risk.status == RiskStatus.REJECTED:
        return (
            f"{classification} {_rejection_text(risk)} "
            "No paper trade was executed and the portfolio is unchanged."
        )

    if not run.trades:
        return (
            f"{classification} The risk engine returned {risk.status.value} but no action survived sizing, "
            "so the portfolio was left unchanged."
        )

    executed: List[str] = []
    for trade in run.trades:
        verb = _ACTION_VERB.get(trade.action, "traded")
        executed.append(f"{verb} {trade.symbol} (${trade.notional:,.0f} notional)")
    executed_text = ", ".join(executed[:-1])
    if len(executed) > 1:
        executed_text = f"{executed_text} and {executed[-1]}"
    else:
        executed_text = executed[0]

    sizing = ""
    if risk.status == RiskStatus.REDUCED:
        detail = _join_reasons(risk.reasons[:2])
        if risk.scale_factor >= 0.999:
            sizing = f" The risk engine trimmed Qwen's proposal before execution ({detail})."
        else:
            sizing = (
                f" The risk engine reduced the requested size to {risk.scale_factor:.0%} of Qwen's proposal "
                f"({detail})."
            )
    else:
        sizing = " All position, exposure, liquidity and volatility checks passed at the requested size."

    return (
        f"{classification} Eventra {executed_text} as a PAPER trade.{sizing} "
        f"Reasoning: {analysis.reasoning_summary}"
    )


def explain_trade(trade: Dict[str, Any]) -> str:
    reason = trade.get("reason") or ""
    return (
        f"{trade.get('action', '')} {trade.get('symbol', '')}: {trade.get('quantity', 0):,.4f} units at "
        f"${trade.get('price', 0):,.2f} (${trade.get('notional', 0):,.0f} notional, PAPER). {reason}"
    ).strip()


def why_symbol(run: DecisionRun, symbol: str) -> Optional[str]:
    """Answer 'Why did Eventra do X to <symbol>?' for the dashboard tooltip."""

    symbol = symbol.upper()
    trade = next((t for t in run.trades if t.symbol == symbol), None)
    if run.analysis is None:
        return None
    impact = next((a for a in run.analysis.affected_assets if a.symbol == symbol), None)
    verdict = run.risk.status.value if run.risk else "NOT_EVALUATED"

    if trade is None:
        return (
            f"Qwen flagged {symbol} as {impact.direction.value if impact else 'affected'} "
            f"(impact {impact.impact_score if impact else 0}/100) but the risk engine returned {verdict}, "
            f"so no {symbol} trade was executed."
        )

    return (
        f"Eventra {trade.action.value.lower()}d {symbol} because Qwen scored the event "
        f"{impact.impact_score if impact else 'n/a'}/100 for {symbol} "
        f"({impact.direction.value if impact else 'neutral'}) with "
        f"{_pct(run.analysis.confidence)} confidence, and the risk engine returned {verdict}. "
        f"{trade.reason}"
    )
