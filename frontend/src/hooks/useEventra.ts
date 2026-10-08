"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  DecisionRun,
  EquityPoint,
  MarketEvent,
  PortfolioView,
  SystemStatus,
  TemplateGroup,
  Trade,
} from "@/lib/types";

export interface Toast {
  id: number;
  message: string;
  kind: "ok" | "warn" | "err";
}

export function useEventra(pollMs = 4000) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [history, setHistory] = useState<EquityPoint[]>([]);
  const [events, setEvents] = useState<MarketEvent[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [decisions, setDecisions] = useState<DecisionRun[]>([]);
  const [templates, setTemplates] = useState<TemplateGroup[]>([]);
  const [activeRun, setActiveRun] = useState<DecisionRun | null>(null);
  const [online, setOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const toastId = useRef(0);
  const failureCount = useRef(0);

  const notify = useCallback((message: string, kind: Toast["kind"] = "ok") => {
    toastId.current += 1;
    const id = toastId.current;
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4200);
  }, []);

  const refreshMarket = useCallback(async () => {
    const [p, h, t] = await Promise.all([
      api.portfolio(),
      api.history(240),
      api.trades(40),
    ]);
    setPortfolio(p);
    setHistory(h);
    setTrades(t);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [s, e, d] = await Promise.all([api.status(), api.events(40), api.decisions(25)]);
      setStatus(s);
      setEvents(e);
      setDecisions(d);
      await refreshMarket();
      setOnline(true);
      setError(null);
      failureCount.current = 0;
    } catch (err) {
      failureCount.current += 1;
      setOnline(false);
      setError(err instanceof Error ? err.message : "Failed to fetch data");
      if (failureCount.current > 3) {
        console.warn("Multiple API failures, check backend connectivity");
      }
      throw err;
    } finally {
      setLoading(false);
    }
  }, [refreshMarket]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
        const groups = await api.templates();
        if (!cancelled) {
          setTemplates(groups);
          setOnline(true);
        }
      } catch {
        if (!cancelled) {
          setOnline(false);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const [s, e] = await Promise.all([api.status(), api.events(40)]);
        setStatus(s);
        setEvents(e);
        await refreshMarket();
        setOnline(true);
        setError(null);
        failureCount.current = 0;
      } catch (err) {
        failureCount.current += 1;
        setOnline(false);
        setError(err instanceof Error ? err.message : "Connection lost");
      }
    }, pollMs);
    return () => clearInterval(id);
  }, [pollMs, refreshMarket]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const watchDecision = useCallback(
    (decisionId: string) => {
      stopPolling();
      let elapsed = 0;
      pollRef.current = setInterval(async () => {
        elapsed += 350;
        try {
          const run = await api.decision(decisionId);
          setActiveRun(run);
          if (run.status !== "running") {
            stopPolling();
            setBusy(false);
            await Promise.all([refreshMarket(), refresh()]);
            const risk = run.risk?.status ?? "UNKNOWN";
            if (risk === "APPROVED" || risk === "REDUCED") {
              notify(`PAPER TRADE EXECUTED - ${run.trades.length} fill(s) - risk ${risk}`, "ok");
            } else if (risk === "REJECTED") {
              notify(`Blocked by risk engine: ${run.risk?.reasons[0] ?? "no reason"}`, "err");
            } else {
              notify(`Decision ${run.status}${run.error ? `: ${run.error}` : ""}`, "warn");
            }
          } else if (elapsed > 30000) {
            stopPolling();
            setBusy(false);
            notify("Timed out waiting for the agent.", "err");
          }
        } catch (err) {
          stopPolling();
          setBusy(false);
          notify(`Polling failed: ${(err as Error).message}`, "err");
        }
      }, 350);
    },
    [notify, refresh, refreshMarket, stopPolling],
  );

  const simulate = useCallback(
    async (templateKey: string) => {
      if (busy) {
        notify("Agent is already working an event.", "warn");
        return;
      }
      setBusy(true);
      setActiveRun(null);
      try {
        const started = await api.simulate(templateKey);
        watchDecision(started.decision_id);
      } catch (err) {
        setBusy(false);
        notify(`Simulation failed: ${(err as Error).message}`, "err");
      }
    },
    [busy, notify, watchDecision],
  );

  const selectEvent = useCallback(
    async (eventId: string) => {
      const match = decisions.find((d) => d.event?.id === eventId);
      if (match) {
        setActiveRun(match);
        return;
      }
      try {
        const all = await api.decisions(50);
        const found = all.find((d) => d.event?.id === eventId);
        if (found) setActiveRun(found);
        else notify("No agent decision recorded for that event yet.", "warn");
      } catch (err) {
        notify((err as Error).message, "err");
      }
    },
    [decisions, notify],
  );

  const toggleKillSwitch = useCallback(async () => {
    const next = !(status?.kill_switch ?? false);
    try {
      await api.killSwitch(next);
      const s = await api.status();
      setStatus(s);
      notify(next ? "KILL SWITCH ARMED - all trading halted." : "Kill switch released - agent resumed.",
        next ? "err" : "ok");
    } catch (err) {
      notify(`Kill switch error: ${(err as Error).message}`, "err");
    }
  }, [notify, status]);

  const reset = useCallback(async () => {
    try {
      await api.reset();
      setActiveRun(null);
      await Promise.all([refresh(), refreshMarket()]);
      notify("Demo state reset.", "ok");
    } catch (err) {
      notify(`Reset failed: ${(err as Error).message}`, "err");
    }
  }, [notify, refresh, refreshMarket]);

  const syncEvents = useCallback(async () => {
    try {
      const result = await api.syncEvents();
      const e = await api.events(40);
      setEvents(e);
      notify(`Ingested ${result.ingested} new event(s) from the provider.`, "ok");
    } catch (err) {
      notify(`Sync failed: ${(err as Error).message}`, "err");
    }
  }, [notify]);

  useEffect(() => stopPolling, [stopPolling]);

  return {
    status, portfolio, history, events, trades, decisions, templates,
    activeRun, online, loading, error, busy, toasts,
    simulate, selectEvent, toggleKillSwitch, reset, syncEvents, notify, refresh,
  };
}