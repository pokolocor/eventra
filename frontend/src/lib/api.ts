import type {
  DecisionRun,
  EquityPoint,
  MarketEvent,
  PortfolioView,
  SystemStatus,
  TemplateGroup,
  Trade,
} from "./types";

/**
 * The browser only ever talks to the Eventra API through same-origin `/api/*`,
 * which Next.js rewrites to the Python backend (see next.config.mjs).
 * No secrets are exposed to the client.
 */
const BASE = process.env.NEXT_PUBLIC_EVENTRA_API_URL?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const detail = (data as { detail?: string } | null)?.detail ?? res.statusText;
    throw new Error(detail);
  }
  return data as T;
}

export const api = {
  status: () => request<SystemStatus>("/api/system/status"),
  health: () => request<{ status: string; mode: string }>("/api/health"),
  portfolio: () => request<PortfolioView>("/api/portfolio"),
  history: (limit = 240) => request<EquityPoint[]>(`/api/portfolio/history?limit=${limit}`),
  trades: (limit = 40) => request<Trade[]>(`/api/portfolio/trades?limit=${limit}`),
  events: (limit = 40) => request<MarketEvent[]>(`/api/events?limit=${limit}`),
  syncEvents: () => request<{ ingested: number }>("/api/events/sync?limit=40", { method: "POST", body: "{}" }),
  templates: () => request<TemplateGroup[]>("/api/agent/templates"),
  decisions: (limit = 25) => request<DecisionRun[]>(`/api/agent/decisions?limit=${limit}`),
  decision: (id: string) => request<DecisionRun>(`/api/agent/decisions/${id}`),
  simulate: (templateKey: string) =>
    request<{ decision_id: string; status: string }>("/api/agent/simulate", {
      method: "POST",
      body: JSON.stringify({ template_key: templateKey }),
    }),
  runSync: (templateKey: string) =>
    request<DecisionRun>("/api/agent/run", {
      method: "POST",
      body: JSON.stringify({ template_key: templateKey }),
    }),
  killSwitch: (engaged: boolean) =>
    request<{ kill_switch: boolean }>("/api/system/kill-switch", {
      method: "POST",
      body: JSON.stringify({ engaged }),
    }),
  reset: () => request<{ ok: boolean }>("/api/system/reset", { method: "POST", body: "{}" }),
  explain: (symbol: string) =>
    request<{ symbol: string; decision_id: string | null; explanation: string }>(
      `/api/agent/explain/${encodeURIComponent(symbol)}`,
    ),
};
