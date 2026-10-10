export type Sentiment = "bullish" | "bearish" | "neutral" | "mixed";
export type MarketRegime = "risk_on" | "risk_off" | "neutral";
export type Direction = "positive" | "negative" | "neutral";
export type TradeAction = "BUY" | "SELL" | "INCREASE" | "REDUCE" | "HOLD" | "HEDGE";
export type RiskStatus = "APPROVED" | "REJECTED" | "REDUCED";
export type CheckResult = "PASS" | "FAIL" | "WARN";
export type StageKey =
  | "event_detected"
  | "qwen_analysis"
  | "market_impact"
  | "signal_generated"
  | "risk_check"
  | "execution"
  | "portfolio_updated";

export interface AssetImpact {
  symbol: string;
  direction: Direction;
  impact_score: number;
}

export interface PortfolioActionProposal {
  symbol: string;
  action: TradeAction;
  percentage: number;
}

export interface MarketEvent {
  id: string;
  timestamp: string;
  title: string;
  source: string;
  category: string;
  summary: string;
  affected_assets: string[];
  importance: "low" | "medium" | "high" | "critical";
  raw: Record<string, unknown>;
  template_key?: string | null;
  is_simulated: boolean;
  analysis_status?: "pending" | "running" | "analysed" | "failed";
  decision?: {
    id: string;
    status: string;
    llm_provider: string;
    risk_status: RiskStatus | null;
    confidence: number | null;
    sentiment: Sentiment | null;
    trade_count: number;
  } | null;
}

export interface QwenAnalysis {
  event_type: string;
  sentiment: Sentiment;
  market_regime: MarketRegime;
  confidence: number;
  affected_assets: AssetImpact[];
  time_horizon: string;
  recommended_action: string;
  portfolio_actions: PortfolioActionProposal[];
  reasoning_summary: string;
  provider: string;
  model: string;
  latency_ms: number;
  attempts: number;
}

export interface RiskDecision {
  status: RiskStatus;
  checks: Record<string, CheckResult>;
  reasons: string[];
  scale_factor: number;
  kill_switch_engaged: boolean;
  approved_actions: PortfolioActionProposal[];
  limits: Record<string, number>;
}

export interface Trade {
  id: string;
  created_at: string;
  symbol: string;
  action: TradeAction;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  notional: number;
  fee: number;
  slippage: number;
  realized_pnl: number;
  reason: string;
  status: string;
  mode: string;
  decision_id?: string | null;
  event_id?: string | null;
}

export interface TimelineEntry {
  stage: StageKey;
  title: string;
  detail: string;
  status: "success" | "warning" | "error";
  timestamp: string;
  duration_ms: number;
}

export interface PositionRow {
  symbol: string;
  name: string;
  asset_class: string;
  sector: string;
  quantity: number;
  avg_entry_price: number;
  last_price: number;
  change_pct: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight_pct: number;
  conviction: number;
  last_signal_id: string | null;
}

export interface PortfolioView {
  starting_balance: number;
  cash: number;
  positions: PositionRow[];
  positions_value: number;
  portfolio_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  total_return_pct: number;
  day_pnl: number;
  day_pnl_pct: number;
  exposure: number;
  gross_exposure: number;
  updated_at: string;
  mode: string;
  kill_switch: boolean;
}

export interface EquityPoint {
  timestamp: string;
  portfolio_value: number;
  cash: number;
  exposure: number;
}

export interface DecisionRun {
  id: string;
  created_at: string;
  status: "running" | "completed" | "failed";
  mode: string;
  llm_provider: string;
  error: string | null;
  explanation: string;
  event: MarketEvent;
  analysis: QwenAnalysis | null;
  signal: Record<string, unknown> | null;
  risk: RiskDecision | null;
  trades: Trade[];
  timeline: TimelineEntry[];
  portfolio_after: PortfolioView | null;
  summary: {
    stage: string;
    risk_status: RiskStatus | null;
    confidence: number | null;
    sentiment: Sentiment | null;
    market_regime: MarketRegime | null;
    recommended_action: string | null;
    trade_count: number;
    symbols: string[];
    stages_completed: string[];
  };
}

export interface EventTemplate {
  key: string;
  label: string;
  group: string;
  category: string;
  importance: string;
  source: string;
  title: string;
  summary: string;
  affected_assets: string[];
  description: string;
}

export interface TemplateGroup {
  group: string;
  templates: EventTemplate[];
}

export interface SystemStatus {
  app: string;
  tagline: string;
  version: string;
  mode: string;
  paper_trading_only: boolean;
  kill_switch: boolean;
  market_tick: number;
  llm: { provider: string; model: string; configured: boolean; base_url: string };
  bitget: { configured: boolean; mode: string };
  database: { url: string; backend: string };
  risk_limits: Record<string, number>;
  counts: { events: number; decisions: number; trades: number; positions: number };
  agent: {
    decisions_total: number;
    decisions_executed: number;
    decisions_rejected: number;
    last_decision_id: string | null;
  };
}

export interface BitgetStatus {
  status: "connected" | "not_configured" | "error";
  message?: string;
  total_balance?: number;
  available_balance?: number;
  positions_count?: number;
  demo_mode: boolean;
  error?: string;
}

export interface PerformanceMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_realized_pnl: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  total_fees: number;
  total_slippage: number;
  risk_violations: number;
  decisions_total: number;
  decisions_executed: number;
  decisions_rejected: number;
  paper_trading_days: number;
  last_updated: string;
}
