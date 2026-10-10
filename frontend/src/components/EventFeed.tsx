"use client";

import { timeAgo } from "@/lib/format";
import type { MarketEvent } from "@/lib/types";

const IMPORTANCE_BORDER: Record<string, string> = {
  critical: "border-l-bear",
  high: "border-l-warn",
  medium: "border-l-info",
  low: "border-l-dim",
};

function StatusPill({ event }: { event: MarketEvent }) {
  const decision = event.decision;
  if (!decision) {
    return (
      <span className="rounded-full border border-edge bg-[#141a24] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.06em] text-dim">
        AWAITING AGENT
      </span>
    );
  }
  const tone =
    event.analysis_status === "analysed"
      ? "border-[#1d5541] bg-[#0f3d2e] text-bull"
      : event.analysis_status === "failed"
        ? "border-[#5d222c] bg-[#3d1620] text-bear"
        : event.analysis_status === "running"
          ? "border-[#1e4a70] bg-[#12283d] text-info"
          : "border-edge bg-[#141a24] text-dim";
  const label = `${String(event.analysis_status).toUpperCase()}${decision.risk_status ? ` · ${decision.risk_status}` : ""}`;
  return (
    <span className={`rounded-full border px-2 py-0.5 font-mono text-[9.5px] tracking-[0.06em] ${tone}`}>
      {label}
    </span>
  );
}

interface Props {
  events: MarketEvent[];
  activeEventId?: string | null;
  onSelect: (eventId: string) => void;
  onSync: () => void;
}

export default function EventFeed({ events, activeEventId, onSelect, onSync }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Live Event Feed</h2>
        <div className="flex items-center gap-2">
          <span className="badge">{events.length} events</span>
          <button type="button" className="btn bg-transparent" onClick={onSync}>
            SYNC
          </button>
        </div>
      </div>
      <div className="panel-body scroll-thin max-h-[520px] overflow-y-auto">
        {events.length === 0 ? (
          <div className="py-8 text-center font-mono text-[11.5px] text-dim">Waiting for events…</div>
        ) : (
          events.map((event) => (
            <button
              key={event.id}
              type="button"
              onClick={() => onSelect(event.id)}
              className={`mb-2 block w-full rounded-md border border-edge border-l-[3px] bg-ink-800 px-3 py-2 text-left transition hover:translate-x-px hover:border-edge-bright hover:bg-[#141d29] ${
                IMPORTANCE_BORDER[event.importance] ?? "border-l-edge-bright"
              } ${activeEventId === event.id ? "ring-1 ring-info/60" : ""}`}
            >
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <StatusPill event={event} />
                <span className="tag">{timeAgo(event.timestamp)}</span>
                <span className="flex-1" />
                <span className="tag">{event.importance}</span>
              </div>
              <h3 className="text-[12.5px] font-semibold leading-snug text-[#eaf1fb]">{event.title}</h3>
              <p className="mt-1 line-clamp-2 text-[11.5px] text-muted">{event.summary}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span className="tag border-[#322a52] text-violet">{event.source}</span>
                <span className="tag">{event.category}</span>
                {event.is_simulated && (
                  <span className="rounded-full border border-[#5a4415] bg-[#3d2c0c]/40 px-1.5 py-0.5 font-mono text-[9px] tracking-[0.06em] text-warn">
                    SIMULATED
                  </span>
                )}
                {event.affected_assets.slice(0, 5).map((symbol) => (
                  <span key={symbol} className="tag tag-sym">
                    {symbol}
                  </span>
                ))}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
