"use client";

import DecisionCenter from "@/components/DecisionCenter";
import DecisionTimeline from "@/components/DecisionTimeline";
import EventFeed from "@/components/EventFeed";
import Explainability from "@/components/Explainability";
import KpiStrip from "@/components/KpiStrip";
import PortfolioChart from "@/components/PortfolioChart";
import PositionsTable from "@/components/PositionsTable";
import SimulatePanel from "@/components/SimulatePanel";
import Toasts from "@/components/Toasts";
import TopBar from "@/components/TopBar";
import { useEventra } from "@/hooks/useEventra";

export default function Page() {
  const agent = useEventra(4000);
  const run = agent.activeRun ?? agent.decisions[0] ?? null;

  return (
    <>
      <TopBar
        status={agent.status}
        online={agent.online}
        onKillSwitch={agent.toggleKillSwitch}
        onReset={agent.reset}
      />

      <main className="mx-auto flex max-w-[1800px] flex-col gap-3.5 px-4 py-3.5 pb-12">
        <KpiStrip portfolio={agent.portfolio} />

        <section className="grid gap-3 lg:grid-cols-2 xl:grid-cols-[minmax(320px,1fr)_minmax(430px,1.35fr)_minmax(300px,1fr)]">
          <EventFeed
            events={agent.events}
            activeEventId={run?.event?.id ?? null}
            onSelect={agent.selectEvent}
            onSync={agent.syncEvents}
          />
          <DecisionCenter run={run} busy={agent.busy} />
          <SimulatePanel groups={agent.templates} busy={agent.busy} onSimulate={agent.simulate} />
        </section>

        <section className="grid gap-3 lg:grid-cols-[1.15fr_1fr]">
          <PortfolioChart history={agent.history} portfolio={agent.portfolio} />
          <PositionsTable portfolio={agent.portfolio} />
        </section>

        <section className="grid gap-3 lg:grid-cols-[1.15fr_1fr]">
          <DecisionTimeline run={run} />
          <Explainability run={run} trades={agent.trades} />
        </section>

        {!agent.online ? (
          <div className="rounded-md border border-[#5d222c] bg-[#1b0f14] px-3 py-2 font-mono text-[11px] text-bear">
            Cannot reach the Eventra API. Start the backend with <b>python backend/run.py</b> (or
            <b> uvicorn backend.main:app</b>) and reload.
          </div>
        ) : null}
      </main>

      <footer className="mt-1.5 border-t border-edge px-4 py-3.5 text-center font-mono text-[10px] tracking-[0.08em] text-dim">
        EVENTRA · autonomous event-driven agent · PAPER TRADING ONLY · no real orders are ever sent
      </footer>

      <Toasts toasts={agent.toasts} />
    </>
  );
}
