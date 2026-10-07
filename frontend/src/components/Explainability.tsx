"use client";

import { clock, money, num } from "@/lib/format";
import type { DecisionRun, Trade } from "@/lib/types";

export default function Explainability({
  run,
  trades,
}: {
  run: DecisionRun | null;
  trades: Trade[];
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Explainability</h2>
        <span className="badge">{run?.mode ?? "PAPER / DEMO"}</span>
      </div>
      <div className="panel-body scroll-thin max-h-[430px] overflow-y-auto">
        {!run || !run.explanation ? (
          <div className="py-6 text-center font-mono text-[11.5px] text-dim">
            Run an event to generate an explanation.
          </div>
        ) : (
          <div className="rounded-md border border-edge border-l-[3px] border-l-violet bg-[#0e0f1a] px-3 py-2.5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-violet">
              Why did Eventra do that?
            </h4>
            <p className="mt-1.5 text-[12px] leading-relaxed text-[#d7e0ee]">{run.explanation}</p>
            <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
              <span>decision <b className="text-[#e6edf7]">{run.id}</b></span>
              <span>risk <b className="text-[#e6edf7]">{run.risk?.status ?? "n/a"}</b></span>
              <span>fills <b className="text-[#e6edf7]">{run.trades.length}</b></span>
              <span>llm <b className="text-[#e6edf7]">{run.llm_provider}</b></span>
              <span>confidence <b className="text-[#e6edf7]">{run.analysis ? `${Math.round(run.analysis.confidence * 100)}%` : "n/a"}</b></span>
            </div>
          </div>
        )}

        <div className="mb-1.5 mt-3 text-[10px] uppercase tracking-[0.14em] text-dim">Trade Blotter · PAPER</div>
        <table className="table-fin">
          <thead>
            <tr>
              <th>Time</th><th>Side</th><th>Asset</th><th>Qty</th><th>Price</th><th>Notional</th><th>Realised</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center text-dim">No trades yet.</td>
              </tr>
            ) : (
              trades.map((trade) => (
                <tr key={trade.id}>
                  <td>{clock(trade.created_at)}</td>
                  <td className={trade.side === "BUY" ? "pos" : "neg"}>{trade.action}</td>
                  <td className="text-cyan2">{trade.symbol}</td>
                  <td>{num(trade.quantity)}</td>
                  <td>{money(trade.price)}</td>
                  <td>{money(trade.notional, 0)}</td>
                  <td className={trade.realized_pnl >= 0 ? "pos" : "neg"}>{money(trade.realized_pnl)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
