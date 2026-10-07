"use client";

import type { TemplateGroup } from "@/lib/types";

const TONE: Record<string, string> = {
  critical: "bg-[#3d1620] text-bear",
  high: "bg-[#3d2c0c] text-warn",
  medium: "bg-[#12283d] text-info",
  low: "bg-[#141a24] text-dim",
};

interface Props {
  groups: TemplateGroup[];
  busy: boolean;
  onSimulate: (templateKey: string) => void;
}

export default function SimulatePanel({ groups, busy, onSimulate }: Props) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Simulate Event</h2>
        <span className={`badge ${busy ? "border-[#5a4415] bg-[#3d2c0c] text-warn" : ""}`}>
          {busy ? "RUNNING" : "READY"}
        </span>
      </div>
      <div className="panel-body scroll-thin max-h-[520px] overflow-y-auto">
        {groups.length === 0 ? (
          <div className="py-8 text-center font-mono text-[11.5px] text-dim">Loading templates…</div>
        ) : (
          groups.map((group) => (
            <div key={group.group}>
              <div className="mb-1.5 mt-2.5 border-b border-edge pb-1 text-[10px] uppercase tracking-[0.14em] text-dim first:mt-0">
                {group.group}
              </div>
              {group.templates.map((template) => (
                <button
                  key={template.key}
                  type="button"
                  disabled={busy}
                  onClick={() => onSimulate(template.key)}
                  className="mb-1.5 block w-full rounded-md border border-edge bg-ink-800 px-2.5 py-2 text-left transition hover:translate-x-0.5 hover:border-info hover:bg-[#131d29] disabled:cursor-progress disabled:opacity-50"
                >
                  <span className="block text-[12px] font-semibold text-[#eaf1fb]">{template.label}</span>
                  <span className="mt-0.5 block text-[10.5px] leading-snug text-muted">
                    {template.description || template.title}
                  </span>
                  <span className="mt-1.5 inline-flex items-center gap-1.5">
                    <span className={`rounded-[3px] px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] ${TONE[template.importance] ?? TONE.low}`}>
                      {template.importance}
                    </span>
                    <span className="tag">{template.category}</span>
                    <span className="tag tag-sym">{template.affected_assets.slice(0, 3).join(" ")}</span>
                  </span>
                </button>
              ))}
            </div>
          ))
        )}
        <p className="mt-3 border-t border-edge pt-2.5 font-mono text-[10px] leading-relaxed text-dim">
          Each click runs the autonomous chain: EVENT → QWEN → SIGNAL → RISK ENGINE → PAPER TRADE → PORTFOLIO UPDATE.
        </p>
      </div>
    </div>
  );
}
