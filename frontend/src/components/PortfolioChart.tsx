"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { clock, compact, money, pct } from "@/lib/format";
import type { EquityPoint, PortfolioView } from "@/lib/types";

interface Props {
  history: EquityPoint[];
  portfolio: PortfolioView | null;
}

export default function PortfolioChart({ history, portfolio }: Props) {
  const data = history.map((point) => ({
    label: clock(point.timestamp),
    value: Number(point.portfolio_value.toFixed(2)),
    exposure: Number(point.exposure.toFixed(2)),
    raw: point,
  }));
  const baseline = portfolio?.starting_balance ?? 0;
  const up = data.length > 0 && data[data.length - 1].value >= baseline;
  const stroke = up ? "#22c58b" : "#ff5c6c";

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Portfolio Value</h2>
        <span className="badge">
          {portfolio ? `${money(portfolio.portfolio_value)}  ${pct(portfolio.total_return_pct)}` : "—"}
        </span>
      </div>
      <div className="panel-body">
        <div className="h-[230px] w-full">
          {data.length < 2 ? (
            <div className="grid h-full place-items-center font-mono text-[11.5px] text-dim">
              Collecting equity curve…
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={stroke} stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#141d29" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#5b6a80", fontSize: 9, fontFamily: "monospace" }}
                  axisLine={{ stroke: "#1c2634" }}
                  tickLine={false}
                  minTickGap={48}
                />
                <YAxis
                  domain={["auto", "auto"]}
                  tickFormatter={(value: number) => compact(value)}
                  tick={{ fill: "#5b6a80", fontSize: 9, fontFamily: "monospace" }}
                  axisLine={false}
                  tickLine={false}
                  width={54}
                />
                <ReferenceLine y={baseline} stroke="#3a4759" strokeDasharray="3 3" />
                <Tooltip
                  isAnimationActive={false}
                  contentStyle={{
                    background: "#0b1119",
                    border: "1px solid #26334a",
                    borderRadius: 5,
                    fontFamily: "monospace",
                    fontSize: 11,
                  }}
                  labelStyle={{ color: "#8494ab" }}
                  formatter={(value: number | string) => [money(Number(value)), "value"]}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={stroke}
                  strokeWidth={1.8}
                  fill="url(#equityFill)"
                  isAnimationActive={false}
                  dot={false}
                  activeDot={{ r: 3.2, fill: stroke, stroke: "#07111a" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
