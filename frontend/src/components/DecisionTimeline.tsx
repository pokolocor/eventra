"use client";

import { clock, human } from "@/lib/format";
import type { DecisionRun } from "@/lib/types";

const DOT: Record<string, string> = {
  success: "bg-bull shadow-[0_0_0_3px_rgba(34,197,139,0.12)]",
  warning: "bg-warn shadow-[0_0_0_3px_rgba(245,166,35,0.12)]",
  error: "bg-bear shadow-[0_0_0_3px_rgba(255,92,108,0.12)]",
};

export default function DecisionTimeline({ run }: { run: DecisionRun | null }) {
  const entries = run?.timeline ?? [];
  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Decision Timeline</h2>
        <span className="badge">{run ? `${entries.length} stages · ${run.id}` : "—"}</span>
      </div>
      <div className="panel-body scroll-thin max-h-[430px] overflow-y-auto">
        {entries.length === 0 ? (
          <div className="py-8 text-center font-mono text-[11.5px] text-dim">No decisions yet.</div>
        ) : (
          entries.map((entry, index) => (
            <div key={`${entry.stage}-${index}`} className="flex gap-2.5 border-b border-dashed border-[#16202c] py-2 last:border-none">
              <div className="w-[62px] flex-none pt-0.5 font-mono text-[9.5px] text-dim">
                {clock(entry.timestamp)}
                <br />
                <span className="text-[#3f4d61]">{entry.duration_ms || 0}ms</span>
              </div>
              <div className={`mt-1.5 h-2.5 w-2.5 flex-none rounded-full ${DOT[entry.status] ?? DOT.success}`} />
              <div className="min-w-0 flex-1">
                <div className="text-[11.5px] font-semibold text-[#eaf1fb]">
                  {entry.title}
                  <span className="ml-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-dim">
                    {human(entry.stage)}
                  </span>
                </div>
                <div className="mt-0.5 break-words text-[11px] text-muted">{entry.detail}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
