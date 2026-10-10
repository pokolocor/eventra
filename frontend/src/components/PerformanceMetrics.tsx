"use client";

import { money, num, pct } from "@/lib/format";
import type { PerformanceMetrics as Metrics } from "@/lib/types";

function MetricCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "neutral";
}) {
  const bar = tone === "up" ? "bg-bull" : tone === "down" ? "bg-bear" : tone === "neutral" ? "bg-warn" : "bg-edge-bright";
  return (
    <div className="relative rounded-md border border-edge bg-[#0c1219] px-3 py-2.5">
      <span className={`absolute left-0 top-0 h-full w-[2px] ${bar}`} />
      <div className="text-[10px] uppercase tracking-[0.14em] text-dim">{label}</div>
      <div className={`mt-1.5 font-mono text-[18px] font-semibold leading-none ${tone === "up" ? "pos" : tone === "down" ? "neg" : tone === "neutral" ? "text-warn" : ""}`}>
        {value}
      </div>
      {sub && <div className="mt-1 font-mono text-[10px] text-muted">{sub}</div>}
    </div>
  );
}

function sharpeTone(value: number): "up" | "down" | "neutral" {
  if (value >= 1.0) return "up";
  if (value >= 0.5) return "neutral";
  return "down";
}

function drawdownTone(value: number): "up" | "down" | "neutral" {
  if (value <= 5) return "up";
  if (value <= 15) return "neutral";
  return "down";
}

function winRateTone(value: number): "up" | "down" | "neutral" {
  if (value >= 55) return "up";
  if (value >= 45) return "neutral";
  return "down";
}

export default function PerformanceMetrics({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) {
    return (
      <div className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Performance Metrics</h2>
        </div>
        <div className="panel-body">
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-[72px] animate-pulse rounded-md border border-edge bg-[#0c1219] opacity-40" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Performance Metrics</h2>
        <span className="font-mono text-[10px] text-dim">
          {metrics.total_trades} trades over {metrics.paper_trading_days} day{metrics.paper_trading_days !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="panel-body">
        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
          <MetricCard
            label="Sharpe Ratio"
            value={metrics.sharpe_ratio.toFixed(2)}
            sub="Annualized risk-adjusted return"
            tone={sharpeTone(metrics.sharpe_ratio)}
          />
          <MetricCard
            label="Sortino Ratio"
            value={metrics.sortino_ratio.toFixed(2)}
            sub="Downside-adjusted return"
            tone={sharpeTone(metrics.sortino_ratio)}
          />
          <MetricCard
            label="Max Drawdown"
            value={pct(metrics.max_drawdown_pct)}
            sub={money(metrics.max_drawdown)}
            tone={drawdownTone(metrics.max_drawdown_pct)}
          />
          <MetricCard
            label="Win Rate"
            value={`${metrics.win_rate.toFixed(1)}%`}
            sub={`${metrics.winning_trades}W / ${metrics.losing_trades}L`}
            tone={winRateTone(metrics.win_rate)}
          />
          <MetricCard
            label="Profit Factor"
            value={metrics.profit_factor.toFixed(2)}
            sub="Gross profit / gross loss"
            tone={metrics.profit_factor >= 1.5 ? "up" : metrics.profit_factor >= 1 ? "neutral" : "down"}
          />
          <MetricCard
            label="Risk Violations"
            value={String(metrics.risk_violations)}
            sub={`${metrics.decisions_rejected} rejected / ${metrics.decisions_total} total`}
            tone={metrics.risk_violations === 0 ? "up" : "neutral"}
          />
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <MetricCard
            label="Avg Win"
            value={money(metrics.avg_win)}
            tone="up"
          />
          <MetricCard
            label="Avg Loss"
            value={money(metrics.avg_loss)}
            tone="down"
          />
          <MetricCard
            label="Largest Win"
            value={money(metrics.largest_win)}
            tone="up"
          />
          <MetricCard
            label="Largest Loss"
            value={money(metrics.largest_loss)}
            tone="down"
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-edge pt-2.5 font-mono text-[10px] text-dim">
          <span>Total realized PnL: <b className={metrics.total_realized_pnl >= 0 ? "pos" : "neg"}>{money(metrics.total_realized_pnl)}</b></span>
          <span>Fees: <b className="text-muted">{money(metrics.total_fees)}</b></span>
          <span>Slippage cost: <b className="text-muted">{money(metrics.total_slippage)}</b></span>
          <span>Decisions executed: <b className="text-muted">{metrics.decisions_executed}/{metrics.decisions_total}</b></span>
        </div>
      </div>
    </div>
  );
}
