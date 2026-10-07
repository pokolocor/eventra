import { money, pct } from "@/lib/format";
import type { PortfolioView } from "@/lib/types";

function Card({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "up" | "down";
}) {
  const bar = tone === "up" ? "bg-bull" : tone === "down" ? "bg-bear" : "bg-edge-bright";
  return (
    <div className="kpi">
      <span className={`absolute left-0 top-0 h-full w-[2px] ${bar}`} />
      <div className="text-[10px] uppercase tracking-[0.14em] text-dim">{label}</div>
      <div className={`mt-1.5 font-mono text-[22px] font-semibold leading-none ${tone === "up" ? "pos" : tone === "down" ? "neg" : ""}`}>
        {value}
      </div>
      <div className="mt-1 font-mono text-[11px] text-muted">{sub}</div>
    </div>
  );
}

export default function KpiStrip({ portfolio }: { portfolio: PortfolioView | null }) {
  if (!portfolio) {
    return (
      <section className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="kpi h-[86px] animate-pulse opacity-40" />
        ))}
      </section>
    );
  }
  return (
    <section className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-5">
      <Card label="Portfolio Value" value={money(portfolio.portfolio_value)} sub={`${portfolio.positions.length} open positions`} />
      <Card
        label="Today's PnL"
        value={money(portfolio.day_pnl)}
        sub={`${pct(portfolio.day_pnl_pct)} vs session open`}
        tone={portfolio.day_pnl >= 0 ? "up" : "down"}
      />
      <Card
        label="Total PnL"
        value={money(portfolio.total_pnl)}
        sub={`${pct(portfolio.total_return_pct)} since inception`}
        tone={portfolio.total_pnl >= 0 ? "up" : "down"}
      />
      <Card
        label="Gross Exposure"
        value={`${portfolio.exposure.toFixed(1)}%`}
        sub={`${money(portfolio.positions_value, 0)} invested / ${money(portfolio.cash, 0)} cash`}
        tone={portfolio.exposure > 85 ? "down" : undefined}
      />
      <Card
        label="Realised PnL"
        value={money(portfolio.realized_pnl)}
        sub={`Unrealised ${money(portfolio.unrealized_pnl)}`}
        tone={portfolio.realized_pnl >= 0 ? "up" : "down"}
      />
    </section>
  );
}
