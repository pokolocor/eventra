"use client";

import { money, num, pct, signed } from "@/lib/format";
import type { PortfolioView } from "@/lib/types";

export default function PositionsTable({ portfolio }: { portfolio: PortfolioView | null }) {
  const rows = portfolio?.positions ?? [];
  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Positions</h2>
        <span className="badge">{rows.length} held</span>
      </div>
      <div className="panel-body scroll-thin max-h-[300px] overflow-y-auto p-0">
        <table className="table-fin">
          <thead>
            <tr>
              <th>Asset</th><th>Qty</th><th>Entry</th><th>Last</th><th>PnL</th><th>Weight</th><th>Conviction</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center text-dim">Flat book.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.symbol}>
                  <td className="text-cyan2">
                    {row.symbol}
                    <div className="text-[9px] font-normal text-dim">{row.asset_class}</div>
                  </td>
                  <td>{num(row.quantity)}</td>
                  <td>{money(row.avg_entry_price)}</td>
                  <td>
                    {money(row.last_price)}{" "}
                    <span className={`text-[9.5px] ${signed(row.change_pct)}`}>{pct(row.change_pct)}</span>
                  </td>
                  <td className={signed(row.unrealized_pnl)}>
                    {money(row.unrealized_pnl)}
                    <div className="text-[9px]">{pct(row.unrealized_pnl_pct)}</div>
                  </td>
                  <td>{row.weight_pct.toFixed(1)}%</td>
                  <td>
                    <span className="inline-block h-[5px] w-11 overflow-hidden rounded-[3px] border border-edge bg-[#0a1017] align-middle">
                      <span
                        className="block h-full bg-gradient-to-r from-[#2b6cb0] to-cyan2"
                        style={{ width: `${Math.round((row.conviction || 0) * 100)}%` }}
                      />
                    </span>{" "}
                    <span className="text-[9.5px] text-muted">{Math.round((row.conviction || 0) * 100)}%</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
