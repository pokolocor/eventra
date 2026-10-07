"""Core Eventra domain types.

Everything the agent reasons about is expressed with these models. Qwen never
touches the portfolio directly: it can only produce a `QwenAnalysis`, which is
validated here, converted into a `Signal`, and then gated by the deterministic
risk engine before the execution service is allowed to act.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventCategory(str, Enum):
    CENTRAL_BANK = "central_bank"
    INFLATION = "inflation"
    EMPLOYMENT = "employment"
    GDP = "gdp"
    EARNINGS = "earnings"
    POLICY = "policy"
    GEOPOLITICAL = "geopolitical"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    MACRO = "macro"
    OTHER = "other"


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


IMPORTANCE_RANK: Dict[str, int] = {
    Importance.LOW.value: 1,
    Importance.MEDIUM.value: 2,
    Importance.HIGH.value: 3,
    Importance.CRITICAL.value: 4,
}


class Sentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class MarketRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SHORT = "1-5 days"
    MEDIUM = "1-4 weeks"
    LONG = "1-6 months"


class RecommendedAction(str, Enum):
    INCREASE_RISK = "increase_risk"
    REDUCE_RISK = "reduce_risk"
    HOLD = "hold"
    HEDGE = "hedge"
    ROTATE = "rotate"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    HEDGE = "HEDGE"


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class RiskStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"


class CheckResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class PipelineStage(str, Enum):
    EVENT_DETECTED = "event_detected"
    QWEN_ANALYSIS = "qwen_analysis"
    MARKET_IMPACT = "market_impact"
    SIGNAL_GENERATED = "signal_generated"
    RISK_CHECK = "risk_check"
    EXECUTION = "execution"
    PORTFOLIO_UPDATED = "portfolio_updated"


class Event(BaseModel):
    """A market-moving event as delivered by a news/macro provider."""

    model_config = ConfigDict(extra="ignore")

    id: str
    timestamp: datetime
    title: str = Field(min_length=3, max_length=300)
    source: str = Field(min_length=1, max_length=120)
    category: EventCategory = EventCategory.OTHER
    summary: str = Field(default="", max_length=4000)
    affected_assets: List[str] = Field(default_factory=list)
    importance: Importance = Importance.MEDIUM
    raw: Dict[str, Any] = Field(default_factory=dict)
    template_key: Optional[str] = None
    is_simulated: bool = False

    @field_validator("affected_assets", mode="before")
    @classmethod
    def _normalise_assets(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [p.strip().upper() for p in value.split(",") if p.strip()]
        return [str(item).strip().upper() for item in value if str(item).strip()]


class AssetImpact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(min_length=1, max_length=16)
    direction: Direction
    impact_score: int = Field(ge=0, le=100)

    @field_validator("symbol", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return str(value).strip().upper()

    @field_validator("impact_score", mode="before")
    @classmethod
    def _coerce_score(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, float):
            # Models sometimes emit 0-1 floats for a 0-100 scale.
            return int(round(value * 100)) if 0.0 <= value <= 1.0 else int(round(value))
        return value


class PortfolioActionProposal(BaseModel):
    """What Qwen would *like* to do. Never executed without a risk check."""

    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(min_length=1, max_length=16)
    action: TradeAction
    percentage: float = Field(ge=0, le=100)

    @field_validator("symbol", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return str(value).strip().upper()

    @field_validator("action", mode="before")
    @classmethod
    def _normalise_action(cls, value: Any) -> Any:
        if isinstance(value, TradeAction):
            return value
        text = str(value).strip().lower().replace(" ", "_")
        aliases = {
            "buy": "BUY",
            "long": "BUY",
            "add": "INCREASE",
            "increase_exposure": "INCREASE",
            "accumulate": "INCREASE",
            "sell": "SELL",
            "exit": "SELL",
            "close": "SELL",
            "reduce_exposure": "REDUCE",
            "trim": "REDUCE",
            "hold": "HOLD",
            "no_action": "HOLD",
            "hedge": "HEDGE",
            "protect": "HEDGE",
        }
        return aliases.get(text, text.upper())


class QwenAnalysis(BaseModel):
    """Validated, structured interpretation of an event produced by Qwen."""

    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(min_length=1, max_length=64)
    sentiment: Sentiment
    market_regime: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    affected_assets: List[AssetImpact] = Field(default_factory=list, min_length=1)
    time_horizon: TimeHorizon = TimeHorizon.SHORT
    recommended_action: RecommendedAction
    portfolio_actions: List[PortfolioActionProposal] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1, max_length=4000)

    # Provenance / observability metadata (filled in by the service layer).
    provider: str = "qwen"
    model: str = "qwen-plus"
    latency_ms: int = 0
    attempts: int = 1
    raw_output: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip().replace("%", "")
            value = float(text) if text else 0.0
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))

    @field_validator("event_type", mode="before")
    @classmethod
    def _normalise_event_type(cls, value: Any) -> Any:
        return str(value).strip().lower().replace(" ", "_") or "other"

    @model_validator(mode="after")
    def _sanitise(self) -> "QwenAnalysis":
        seen: Dict[str, PortfolioActionProposal] = {}
        for action in self.portfolio_actions:
            if action.action == TradeAction.HOLD or action.percentage <= 0:
                continue
            seen[action.symbol] = action
        self.portfolio_actions = list(seen.values())
        return self


class Signal(BaseModel):
    """The tradeable signal derived from a validated analysis."""

    id: str
    event_id: str
    created_at: datetime = Field(default_factory=utcnow)
    sentiment: Sentiment
    market_regime: MarketRegime
    recommended_action: RecommendedAction
    confidence: float
    time_horizon: TimeHorizon
    affected_assets: List[AssetImpact]
    proposed_actions: List[PortfolioActionProposal]
    reasoning_summary: str
    provider: str = "qwen"
    model: str = "qwen-plus"


class RiskDecision(BaseModel):
    status: RiskStatus
    checks: Dict[str, CheckResult]
    reasons: List[str] = Field(default_factory=list)
    approved_actions: List[PortfolioActionProposal] = Field(default_factory=list)
    scale_factor: float = 1.0
    limits: Dict[str, Any] = Field(default_factory=dict)
    kill_switch_engaged: bool = False

    def to_public_dict(self) -> Dict[str, Any]:
        """Shape advertised in the README: {"status": ..., "checks": {...}}."""

        return {
            "status": self.status.value,
            "checks": {name: result.value for name, result in self.checks.items()},
            "reasons": self.reasons,
            "scale_factor": round(self.scale_factor, 4),
            "kill_switch_engaged": self.kill_switch_engaged,
            "approved_actions": [a.model_dump(mode="json") for a in self.approved_actions],
            "limits": self.limits,
        }


class Position(BaseModel):
    symbol: str
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    last_price: float = 0.0
    conviction: float = 0.0
    last_signal_id: Optional[str] = None
    opened_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.avg_entry_price) * self.quantity


class Trade(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=utcnow)
    decision_id: Optional[str] = None
    event_id: Optional[str] = None
    symbol: str
    action: TradeAction
    side: TradeSide
    quantity: float
    price: float
    notional: float
    fee: float = 0.0
    slippage: float = 0.0
    realized_pnl: float = 0.0
    reason: str = ""
    status: str = "FILLED"
    mode: str = "PAPER"


class EquityPoint(BaseModel):
    timestamp: datetime
    portfolio_value: float
    cash: float
    exposure: float


class PortfolioSnapshot(BaseModel):
    starting_balance: float
    cash: float
    positions: List[Position] = Field(default_factory=list)
    positions_value: float = 0.0
    portfolio_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    day_pnl: float = 0.0
    day_pnl_pct: float = 0.0
    exposure: float = 0.0
    gross_exposure: float = 0.0
    updated_at: datetime = Field(default_factory=utcnow)


class TimelineEntry(BaseModel):
    stage: PipelineStage
    title: str
    detail: str = ""
    status: str = "success"
    timestamp: datetime = Field(default_factory=utcnow)
    duration_ms: int = 0
    payload: Dict[str, Any] = Field(default_factory=dict)


class DecisionRun(BaseModel):
    """One full pass through Event -> Qwen -> Signal -> Risk -> Execution."""

    id: str
    created_at: datetime = Field(default_factory=utcnow)
    event: Event
    analysis: Optional[QwenAnalysis] = None
    signal: Optional[Signal] = None
    risk: Optional[RiskDecision] = None
    trades: List[Trade] = Field(default_factory=list)
    timeline: List[TimelineEntry] = Field(default_factory=list)
    explanation: str = ""
    status: str = "completed"
    error: Optional[str] = None
    portfolio_after: Optional[PortfolioSnapshot] = None
    mode: str = "PAPER"
    llm_provider: str = "demo"
