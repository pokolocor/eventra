"use client";

import { clock, human, money, num } from "@/lib/format";
import type { DecisionRun, RiskStatus, StageKey } from "@/lib/types";

const CHAIN_STAGES: { key: StageKey; label: string; n: string; also?: StageKey[] }[] = [
  { key: "event_detected", label: "Event Detected", n: "1" },
  { key: "qwen_analysis", label: "Qwen Analysis", n: "2" },
  { key: "market_impact", label: "Market Impact", n: "3", also: ["signal_generated"] },
  { key: "risk_check", label: "Risk Check", n: "4" },
  { key: "execution", label: "Execution", n: "5", also: ["portfolio_updated"] },
];

const VERDICT_TONE: Record<string, string> = {
  APPROVED: "border-[#1d5541] bg-[#0f3d2e] text-bull",
  REDUCED: "border-[#5a4415] bg-[#3d2c0c] text-warn",
  REJECTED: "border-[#5d222c] bg-[#3d1620] text-bear",
  RUNNING: "border-[#1e4a70] bg-[#12283d] text-info",
  FAILED: "border-[#5d222c] bg-[#3d1620] text-bear",
};

const CHECK_TONE: Record<string, string> = {
  PASS: "border-[#153c2e] text-bull",
  WARN: "border-[#4a380f] text-warn",
  FAIL: "border-[#4d1d26] text-bear",
};

function entriesFor(run: DecisionRun, key: StageKey, also?: StageKey[]) {
  const wanted: StageKey[] = [key, ...(also ?? [])];
  return run.timeline.filter((entry) => wanted.includes(entry.stage));
}

function Verdict({ value }: { value: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded border px-2.5 py-1 font-mono text-[11px] font-bold tracking-[0.14em] ${
        VERDICT_TONE[value] ?? VERDICT_TONE.RUNNING
      }`}
    >
      {value}
    </span>
  );
}

function Chain({ run }: { run: DecisionRun | null }) {
  return (
    <div className="mb-3 flex flex-col">
      {CHAIN_STAGES.map((stage, index) => {
        const entries = run ? entriesFor(run, stage.key, stage.also) : [];
        const primary = entries[0];
        const reachedBefore =
          run !== null && CHAIN_STAGES.slice(0, index).some((s) => entriesFor(run, s.key, s.also).length > 0);
        const stateClass = primary
          ? primary.status === "error"
            ? "border-[#5d222c] bg-[#1b0f14]"
            : primary.status === "warning"
              ? "border-[#5a4415] bg-[#1a1509]"
              : "border-[#1e3a55] bg-[#101a26]"
          : run?.status === "running" && reachedBefore
            ? "border-[#1e3a55] bg-[#101a26]"
            : "border-transparent opacity-40";
        const dotTone = primary
          ? primary.status === "error"
            ? "border-[#5d222c] bg-[#3d1620] text-bear"
            : primary.status === "warning"
              ? "border-[#5a4415] bg-[#3d2c0c] text-warn"
              : "border-[#1d5541] bg-[#0f3d2e] text-bull"
          : run?.status === "running" && reachedBefore
            ? "animate-ring border-info bg-[#12283d] text-info"
            : "border-edge-bright bg-[#111a25] text-dim";
        const detail = entries.map((e) => e.detail).filter(Boolean).join(" — ");

        return (
          <div key={stage.key} className={`flex items-start gap-2.5 rounded-md border px-2.5 py-2 transition ${stateClass}`}>
            <div className="flex flex-none flex-col items-center">
              <div className={`grid h-5 w-5 place-items-center rounded-full border font-mono text-[10px] ${dotTone}`}>
                {stage.n}
              </div>
              {index < CHAIN_STAGES.length - 1 && <div className="my-0.5 h-4 w-px bg-edge-bright" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{stage.label}</div>
                <span className="flex-1" />
                {primary?.duration_ms ? (
                  <div className="font-mono text-[9.5px] text-dim">{primary.duration_ms}ms</div>
                ) : null}
              </div>
              <div className="mt-0.5 break-words text-[11.5px] text-[#e6edf7]">
                {primary ? `${primary.title}${detail ? `: ${detail}` : ""}` : run?.status === "running" ? "Working…" : "Waiting…"}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ImpactBars({ run }: { run: DecisionRun }) {
  const assets = [...(run.analysis?.affected_assets ?? [])].sort((a, b) => b.impact_score - a.impact_score);
  return (
    <div className="mt-2">
      {assets.map((asset) => (
        <div key={asset.symbol} className="mb-1.5 flex items-center gap-2 font-mono text-[11px]">
          <span className="w-[52px] font-semibold">{asset.symbol}</span>
          <span className="h-[6px] flex-1 overflow-hidden rounded-[3px] border border-edge bg-[#0a1017]">
            <span
              className={`block h-full transition-all duration-500 ${
                asset.direction === "positive"
                  ? "bg-gradient-to-r from-[#17795a] to-bull"
                  : asset.direction === "negative"
                    ? "bg-gradient-to-r from-[#8c2b38] to-bear"
                    : "bg-gradient-to-r from-[#3a4759] to-muted"
              }`}
              style={{ width: `${asset.impact_score}%` }}
            />
          </span>
          <span
            className={`w-[38px] text-right ${
              asset.direction === "positive" ? "pos" : asset.direction === "negative" ? "neg" : "neu"
            }`}
          >
            {asset.direction === "positive" ? "+" : asset.direction === "negative" ? "-" : ""}
            {asset.impact_score}
          </span>
        </div>
      ))}
    </div>
  );
}

function AnalysisPanel({ run }: { run: DecisionRun }) {
  const a = run.analysis;
  if (!a) return null;
  return (
    <div className="mt-3 rounded-md border border-edge border-l-[3px] border-l-cyan2 bg-[#0b141c] px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan2">Market Impact</h4>
        <span className="font-mono text-[9.5px] text-dim">
          {a.provider} / {a.model} · {a.latency_ms}ms · {a.attempts} attempt{a.attempts === 1 ? "" : "s"}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
        <span>type <b className="text-[#e6edf7]">{human(a.event_type)}</b></span>
        <span>sentiment <b className="text-[#e6edf7]">{a.sentiment}</b></span>
        <span>regime <b className="text-[#e6edf7]">{human(a.market_regime)}</b></span>
        <span>confidence <b className="text-[#e6edf7]">{Math.round(a.confidence * 100)}%</b></span>
        <span>horizon <b className="text-[#e6edf7]">{a.time_horizon}</b></span>
        <span>action <b className="text-[#e6edf7]">{human(a.recommended_action)}</b></span>
      </div>
      <ImpactBars run={run} />
      <div className="mt-2.5 text-[10px] uppercase tracking-[0.14em] text-dim">
        Proposed portfolio actions (unvalidated)
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {a.portfolio_actions.length === 0 ? (
          <span className="tag">NO CHANGE</span>
        ) : (
          a.portfolio_actions.map((action) => (
            <span
              key={`${action.symbol}-${action.action}`}
              className={`tag ${action.action === "REDUCE" || action.action === "SELL" ? "border-[#4d1d26] text-bear" : "tag-sym"}`}
            >
              {action.action} {action.symbol} {action.percentage.toFixed(0)}%
            </span>
          ))
        )}
      </div>
      <p className="mt-2.5 text-[12px] leading-relaxed text-[#d7e0ee]">{a.reasoning_summary}</p>
    </div>
  );
}

function RiskPanel({ run }: { run: DecisionRun }) {
  const risk = run.risk;
  if (!risk) return null;
  const tone =
    risk.status === "APPROVED" ? "border-l-bull" : risk.status === "REDUCED" ? "border-l-warn" : "border-l-bear";
  return (
    <div className={`mt-3 rounded-md border border-edge border-l-[3px] bg-[#0c1219] px-3 py-2.5 ${tone}`}>
      <div className="flex items-center gap-3">
        <Verdict value={risk.status} />
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-muted">
          size scale <b className="text-[#e6edf7]">{Math.round((risk.scale_factor ?? 0) * 100)}%</b>
        </span>
        {risk.kill_switch_engaged ? <span className="tag border-[#5d222c] text-bear">KILL SWITCH</span> : null}
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4">
        {Object.entries(risk.checks).map(([name, result]) => (
          <div
            key={name}
            className={`flex items-center justify-between gap-1.5 rounded border bg-[#0a1017] px-2 py-1.5 font-mono text-[10px] ${CHECK_TONE[result] ?? "border-edge"}`}
          >
            <span className="truncate text-muted">{human(name)}</span>
            <span className="font-bold tracking-[0.08em]">{result}</span>
          </div>
        ))}
      </div>
      <div className="mt-2.5 text-[10px] uppercase tracking-[0.14em] text-dim">Approved for execution</div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {risk.approved_actions.length === 0 ? (
          <span className="tag">NONE</span>
        ) : (
          risk.approved_actions.map((action) => (
            <span key={`${action.symbol}-${action.action}`} className="tag tag-sym">
              {action.action} {action.symbol} {action.percentage.toFixed(1)}%
            </span>
          ))
        )}
      </div>
      {risk.reasons.length > 0 && (
        <ul className="mt-2.5 space-y-0.5">
          {risk.reasons.map((reason, index) => (
            <li key={index} className="relative pl-3.5 text-[11px] text-muted before:absolute before:left-0 before:text-dim before:content-['▸']">
              {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FillsPanel({ run }: { run: DecisionRun }) {
  if (!run.risk) return null;
  if (run.trades.length === 0) {
    return <div className="py-5 text-center font-mono text-[11.5px] text-dim">No paper trade executed for this decision.</div>;
  }
  return (
    <div className="mt-3">
      <div className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-dim">Execution · PAPER</div>
      <table className="table-fin">
        <thead>
          <tr>
            <th>Asset</th><th>Action</th><th>Qty</th><th>Fill</th><th>Notional</th><th>Slip</th><th>Fee</th>
          </tr>
        </thead>
        <tbody>
          {run.trades.map((trade) => (
            <tr key={trade.id}>
              <td className="text-cyan2">{trade.symbol}</td>
              <td className={trade.side === "BUY" ? "pos" : "neg"}>{trade.action}</td>
              <td>{num(trade.quantity)}</td>
              <td>{money(trade.price)}</td>
              <td>{money(trade.notional, 0)}</td>
              <td>{(trade.slippage * 100).toFixed(3)}%</td>
              <td>{money(trade.fee)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  run: DecisionRun | null;
  busy: boolean;
}

export default function DecisionCenter({ run, busy }: Props) {
  const verdict: RiskStatus | "RUNNING" | "FAILED" = !run
    ? "RUNNING"
    : run.status === "running"
      ? "RUNNING"
      : run.risk
        ? run.risk.status
        : "FAILED";

  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Agent Decision Center</h2>
        <div className="flex items-center gap-2">
          {busy && <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-[#1e4a70] border-t-info" />}
          <Verdict value={verdict} />
        </div>
      </div>
      <div className="panel-body scroll-thin max-h-[620px] overflow-y-auto">
        <Chain run={run} />
        {!run ? (
          <div className="py-8 text-center font-mono text-[11.5px] leading-relaxed text-dim">
            Run an event from the simulator to watch the full
            <br />
            EVENT → QWEN → IMPACT → RISK → EXECUTION chain.
          </div>
        ) : (
          <>
            <div className="rounded-md border border-edge border-l-[3px] border-l-violet bg-[#0e0f1a] px-3 py-2.5">
              <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-violet">Event</h4>
              <p className="mt-1 text-[12px] font-semibold text-[#eaf1fb]">{run.event?.title}</p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
                <span>id <b className="text-[#e6edf7]">{run.event?.id}</b></span>
                <span>source <b className="text-[#e6edf7]">{run.event?.source}</b></span>
                <span>category <b className="text-[#e6edf7]">{run.event?.category}</b></span>
                <span>importance <b className="text-[#e6edf7]">{String(run.event?.importance ?? "").toUpperCase()}</b></span>
                <span>at <b className="text-[#e6edf7]">{run.event ? clock(run.event.timestamp) : ""}</b></span>
              </div>
            </div>
            <AnalysisPanel run={run} />
            <RiskPanel run={run} />
            <FillsPanel run={run} />
            {run.error ? (
              <div className="mt-3 rounded-md border border-[#5d222c] bg-[#1b0f14] px-3 py-2 font-mono text-[11px] text-bear">
                {run.error}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
