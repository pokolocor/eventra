import type { SystemStatus } from "@/lib/types";

interface Props {
  status: SystemStatus | null;
  online: boolean;
  onKillSwitch: () => void;
  onReset: () => void;
}

export default function TopBar({ status, online, onKillSwitch, onReset }: Props) {
  const kill = status?.kill_switch ?? false;
  const llm = status?.llm;
  return (
    <header className="sticky top-0 z-40 flex flex-wrap items-center justify-between gap-4 border-b border-edge bg-ink-950/92 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-md border border-[#2b4a6b] bg-gradient-to-br from-[#12324f] to-[#1b1030] text-[17px] text-cyan2 shadow-[0_0_18px_rgba(55,208,216,0.18)]">
          &#9670;
        </div>
        <div>
          <h1 className="text-[19px] font-bold leading-none tracking-[0.24em]">EVENTRA</h1>
          <p className="mt-0.5 text-[10.5px] uppercase tracking-[0.14em] text-muted">
            From Events to Execution
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="badge border-[#5a4415] bg-[#3d2c0c] text-warn">
          {status?.mode ?? "PAPER / DEMO"}
        </span>
        <span
          className={`badge ${
            llm?.provider === "qwen" ? "border-[#1d5541] bg-[#0f3d2e] text-bull" : "border-[#5a4415] bg-[#3d2c0c] text-warn"
          }`}
        >
          LLM {llm?.provider === "qwen" ? `QWEN ${llm.model}` : "DEMO MOCK"}
        </span>
        <span className="badge">STORE {String(status?.database?.backend ?? "?").toUpperCase()}</span>
        <span className="badge">
          {status ? `TICK ${status.market_tick}` : "TICK —"}
        </span>
        <span className={`badge ${online ? "border-[#1d5541] bg-[#0f3d2e] text-bull" : "border-[#5d222c] bg-[#3d1620] text-bear"}`}>
          {online ? "LIVE" : "OFFLINE"}
        </span>
        <button
          type="button"
          onClick={onKillSwitch}
          title="Global emergency stop - halts every new trade"
          className={`btn border-[#5d222c] bg-[#1a0d12] text-[#ff9aa5] ${kill ? "animate-pulseRed bg-bear font-bold text-[#12060a]" : ""}`}
        >
          {kill ? "KILL SWITCH ARMED" : "KILL SWITCH"}
        </button>
        <button type="button" onClick={onReset} className="btn bg-transparent">
          RESET
        </button>
      </div>
    </header>
  );
}
