/* Eventra demo terminal - talks to the same REST API as the Next.js app. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const CHAIN_STAGES = [
  { key: "event_detected", label: "Event Detected", n: "1" },
  { key: "qwen_analysis", label: "Qwen Analysis", n: "2" },
  { key: "market_impact", label: "Market Impact", n: "3", also: ["signal_generated"] },
  { key: "risk_check", label: "Risk Check", n: "4" },
  { key: "execution", label: "Execution", n: "5", also: ["portfolio_updated"] },
];

const state = {
  status: null,
  portfolio: null,
  history: [],
  events: [],
  decisions: [],
  trades: [],
  templates: [],
  activeDecision: null,
  polling: null,
  killSwitch: false,
  online: false,
};

/* ---------------- formatting ---------------- */
const money = (v, dp = 2) =>
  (v < 0 ? "-$" : "$") + Math.abs(Number(v) || 0).toLocaleString("en-US", {
    minimumFractionDigits: dp, maximumFractionDigits: dp,
  });
const compact = (v) => {
  const n = Math.abs(Number(v) || 0);
  if (n >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
};
const pct = (v, dp = 2) => (Number(v) >= 0 ? "+" : "") + Number(v).toFixed(dp) + "%";
const num = (v, dp = 4) => Number(v || 0).toLocaleString("en-US", { maximumFractionDigits: dp });
const cls = (v) => (Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "neu");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function timeAgo(iso) {
  const then = new Date(iso).getTime();
  if (!then) return "";
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return Math.floor(secs) + "s ago";
  if (secs < 3600) return Math.floor(secs / 60) + "m ago";
  if (secs < 86400) return Math.floor(secs / 3600) + "h ago";
  return Math.floor(secs / 86400) + "d ago";
}
const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour12: false });

/* ---------------- transport ---------------- */
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = { detail: text }; }
  if (!res.ok) throw new Error((data && data.detail) || res.statusText);
  return data;
}

function toast(message, kind = "ok") {
  const wrap = $("#toast");
  const el = document.createElement("div");
  el.className = "toast" + (kind === "ok" ? "" : " " + kind);
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, 3600);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- boot ---------------- */
async function loadAll() {
  await refreshStatus();
  await Promise.all([
    refreshPortfolio(), refreshEvents(), refreshTemplates(),
    refreshDecisions(), refreshTrades(),
  ]);
}

async function boot() {
  renderChainShell();
  try {
    await loadAll();
    setConn(true);
    state.online = true;
  } catch (err) {
    state.online = false;
    setConn(false);
    showOfflineBanner(err && err.message);
  }
  setInterval(tick, 4000);
  // Load new features
  loadMarketStatus();
  loadArbitrage();
  loadMetrics();
  loadBitgetMarketData();
  setInterval(() => {
    loadMarketStatus();
    loadArbitrage();
    loadMetrics();
    loadBitgetMarketData();
  }, 30000); // Refresh every 30s
}

function showOfflineBanner(reason) {
  let el = document.getElementById("offlineBanner");
  if (!el) {
    el = document.createElement("div");
    el.id = "offlineBanner";
    el.className = "offline-banner";
    el.innerHTML =
      '<div class="ob-text"><span class="ob-dot"></span>' +
      '<strong>Cannot reach the Eventra API.</strong>' +
      '<span class="ob-sub">The local server is not running. Start it, then Eventra reconnects automatically.</span></div>' +
      '</div>' +
      '<button class="ob-btn" type="button">RETRY NOW</button>';
    el.querySelector(".ob-btn").addEventListener("click", () => { tick(); });
    document.body.insertBefore(el, document.body.firstChild);
  }
  const sub = el.querySelector(".ob-sub");
  if (sub && reason) sub.textContent = "Retrying every 4s - " + reason;
  el.style.display = "flex";
}

function hideOfflineBanner() {
  const el = document.getElementById("offlineBanner");
  if (el) el.style.display = "none";
}

function setConn(ok) {
  const el = $("#connBadge");
  if (!el) return;
  el.textContent = ok ? "LIVE" : "OFFLINE";
  el.className = "badge " + (ok ? "ok" : "err");
}

async function refreshStatus() {
  state.status = await api("/api/system/status");
  state.killSwitch = !!state.status.kill_switch;
  const modeEl = $("#modeBadge"); if (modeEl) modeEl.textContent = state.status.mode || "PAPER / DEMO";
  const llm = state.status.llm || {};
  const llmEl = $("#llmBadge"); if (llmEl) {
    llmEl.textContent = "LLM " + (llm.provider === "qwen" ? "QWEN " + (llm.model || "") : "DEMO MOCK");
    llmEl.className = "badge " + (llm.provider === "qwen" ? "ok" : "warn");
  }
  const news = state.status.news || {};
  const newsEl = $("#newsBadge"); if (newsEl) {
    newsEl.textContent = "NEWS " + (news.live ? "LIVE (" + news.provider.toUpperCase() + ")" : "DEMO");
    newsEl.className = "badge " + (news.live ? "ok" : "warn");
  }
  const npEl = $("#newsProvider"); if (npEl) {
    npEl.textContent = news.live ? "LIVE" : "DEMO";
    npEl.className = "badge " + (news.live ? "ok" : "warn");
  }
  const dbEl = $("#dbBadge"); if (dbEl) dbEl.textContent = "STORE " + String((state.status.database || {}).backend || "?").toUpperCase();
  const ks = $("#killSwitch");
  if (ks) {
    ks.classList.toggle("armed", state.killSwitch);
    ks.textContent = state.killSwitch ? "KILL SWITCH ARMED" : "KILL SWITCH";
  }
}

async function tick() {
  const wasOnline = state.online;
  try {
    if (wasOnline) {
      await refreshStatus();
      await Promise.all([refreshPortfolio(), refreshEvents(), refreshTrades()]);
    } else {
      await loadAll();
    }
    state.online = true;
    setConn(true);
    hideOfflineBanner();
    if (!wasOnline && state.status) toast("Reconnected to the Eventra API", "ok");
  } catch (_) {
    if (wasOnline) {
      toast("Lost connection to the Eventra API - retrying...", "err");
      showOfflineBanner("connection lost");
    }
    state.online = false;
    setConn(false);
  }
}

/* ---------------- KPIs ---------------- */
async function refreshPortfolio() {
  const p = await api("/api/portfolio");
  state.portfolio = p;
  renderKpis(p);
  renderPositions(p);
  const history = await api("/api/portfolio/history?limit=240");
  state.history = history;
  renderChart(history, p);
}

function kpiCard(label, value, sub, tone) {
  return `<div class="kpi ${tone || ""}"><div class="label">${label}</div>
    <div class="value ${tone === "up" ? "pos" : tone === "down" ? "neg" : ""}">${value}</div>
    <div class="sub">${sub || ""}</div></div>`;
}

function renderKpis(p) {
  $("#kpis").innerHTML = [
    kpiCard("Portfolio Value", money(p.portfolio_value), `${p.positions.length} open positions`, ""),
    kpiCard("Today's PnL", money(p.day_pnl), `${pct(p.day_pnl_pct)} vs session open`, p.day_pnl >= 0 ? "up" : "down"),
    kpiCard("Total PnL", money(p.total_pnl), `${pct(p.total_return_pct)} since inception`, p.total_pnl >= 0 ? "up" : "down"),
    kpiCard("Gross Exposure", Number(p.exposure).toFixed(1) + "%",
      `${money(p.positions_value)} invested / ${money(p.cash)} cash`, p.exposure > 85 ? "down" : ""),
    kpiCard("Realised PnL", money(p.realized_pnl), `Unrealised ${money(p.unrealized_pnl)}`,
      p.realized_pnl >= 0 ? "up" : "down"),
  ].join("");
  const posMetaEl = $("#posMeta"); if (posMetaEl) posMetaEl.textContent = `${p.positions.length} held`;
  const chartMetaEl = $("#chartMeta"); if (chartMetaEl) chartMetaEl.textContent = `${money(p.portfolio_value)}  ${pct(p.total_return_pct)}`;
}

function renderPositions(p) {
  const table = $("#positions");
  if (!table) return;
  const rows = p.positions.map((r) => `
    <tr>
      <td class="sym">${esc(r.symbol)}<div style="font-size:9px;color:var(--dim);font-weight:400">${esc(r.asset_class)}</div></td>
      <td>${num(r.quantity)}</td>
      <td>${money(r.avg_entry_price)}</td>
      <td>${money(r.last_price)} <span class="${cls(r.change_pct)}" style="font-size:9.5px">${pct(r.change_pct, 2)}</span></td>
      <td class="${cls(r.unrealized_pnl)}">${money(r.unrealized_pnl)}<div style="font-size:9px">${pct(r.unrealized_pnl_pct)}</div></td>
      <td>${Number(r.weight_pct).toFixed(1)}%</td>
      <td><span class="conv"><i style="width:${Math.round((r.conviction || 0) * 100)}%"></i></span>
        <span style="font-size:9.5px;color:var(--muted)">${Math.round((r.conviction || 0) * 100)}%</span></td>
    </tr>`).join("");
  table.querySelector("tbody").innerHTML = rows || `<tr><td colspan="7" class="empty">Flat book.</td></tr>`;
}

/* ---------------- portfolio chart ---------------- */
function renderChart(history, p) {
  const svg = $("#chart");
  if (!history || history.length < 2) {
    svg.innerHTML = "";
    return;
  }
  const W = 1000, H = 230, PAD_L = 54, PAD_R = 12, PAD_T = 12, PAD_B = 20;
  const values = history.map((h) => h.portfolio_value);
  const base = p ? p.starting_balance : values[0];
  const lo = Math.min(...values, base);
  const hi = Math.max(...values, base);
  const pad = (hi - lo) * 0.15 || Math.max(1, hi * 0.01);
  const min = lo - pad, max = hi + pad;
  const x = (i) => PAD_L + (i / (history.length - 1)) * (W - PAD_L - PAD_R);
  const y = (v) => PAD_T + (1 - (v - min) / (max - min)) * (H - PAD_T - PAD_B);

  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const val = min + ((max - min) * g) / 4;
    const gy = y(val);
    grid += `<line class="grid-line" x1="${PAD_L}" y1="${gy}" x2="${W - PAD_R}" y2="${gy}"/>
      <text class="axis-label" x="${PAD_L - 8}" y="${gy + 3}" text-anchor="end">${compact(val)}</text>`;
  }
  const line = history.map((h, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(h.portfolio_value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(history.length - 1).toFixed(1)},${H - PAD_B} L${PAD_L},${H - PAD_B} Z`;
  const baseY = y(base);
  const up = values[values.length - 1] >= base;

  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = `
    <defs>
      <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${up ? "#22c58b" : "#ff5c6c"}" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="${up ? "#22c58b" : "#ff5c6c"}" stop-opacity="0.01"/>
      </linearGradient>
    </defs>
    ${grid}
    <line class="baseline" x1="${PAD_L}" y1="${baseY}" x2="${W - PAD_R}" y2="${baseY}"/>
    <text class="axis-label" x="${W - PAD_R}" y="${baseY - 5}" text-anchor="end">start ${compact(base)}</text>
    <path class="area-fill" d="${area}"/>
    <path class="area-line" d="${line}" style="stroke:${up ? "#22c58b" : "#ff5c6c"}"/>
    <circle cx="${x(history.length - 1)}" cy="${y(values[values.length - 1])}" r="3.2"
      fill="${up ? "#22c58b" : "#ff5c6c"}" stroke="#07111a" stroke-width="1.4"/>`;

  const tip = $("#chartTip");
  svg.onmousemove = (ev) => {
    const rect = svg.getBoundingClientRect();
    const ratio = (ev.clientX - rect.left) / rect.width;
    const idx = Math.max(0, Math.min(history.length - 1,
      Math.round((ratio * W - PAD_L) / (W - PAD_L - PAD_R) * (history.length - 1))));
    const point = history[idx];
    tip.style.opacity = "1";
    tip.style.left = Math.min(rect.width - 150, ratio * rect.width) + "px";
    tip.style.top = (y(point.portfolio_value) / H) * rect.height - 12 + "px";
    tip.innerHTML = `${money(point.portfolio_value)}<br/><span style="color:var(--dim)">
      exp ${Number(point.exposure).toFixed(1)}% &middot; ${clock(point.timestamp)}</span>`;
  };
  svg.onmouseleave = () => { tip.style.opacity = "0"; };
}

/* ---------------- event feed ---------------- */
async function refreshEvents() {
  const events = await api("/api/events?limit=40");
  const previous = new Set(state.events.map((e) => e.id));
  state.events = events;
  renderFeed(events, previous.size > 0);
  $("#eventCount").textContent = `${events.length} events`;
}

function renderFeed(events, animateNew) {
  if (!events.length) { $("#eventFeed").innerHTML = `<div class="empty">No events yet. Click SYNC to fetch live news.</div>`; return; }
  $("#eventFeed").innerHTML = events.map((e) => {
    const decision = e.decision;
    const isLive = e.raw && e.raw.provider && e.raw.provider !== "demo" && e.raw.provider !== "eventra-simulator";
    const liveBadge = isLive ? `<span class="tag live">LIVE</span>` : "";
    const pill = decision
      ? `<span class="pill ${e.analysis_status}">${e.analysis_status.toUpperCase()}${
          decision.risk_status ? " &middot; " + decision.risk_status : ""}</span>`
      : `<span class="pill pending">AWAITING AGENT</span>`;
    const symbols = (e.affected_assets || []).slice(0, 5)
      .map((s) => `<span class="tag sym">${esc(s)}</span>`).join("");
    return `<div class="event imp-${esc(e.importance)}" data-id="${esc(e.id)}"
        data-template="${esc((e.raw || {}).template_key || "")}">
      <div class="event-top">${pill}${liveBadge}<span class="tag time">${timeAgo(e.timestamp)}</span>
        <span class="spacer"></span><span class="tag">${esc(e.importance)}</span></div>
      <h3>${esc(e.title)}</h3>
      <p>${esc(e.summary)}</p>
      <div class="event-meta"><span class="tag src">${esc(e.source)}</span>
        <span class="tag">${esc(e.category)}</span>${symbols}</div>
    </div>`;
  }).join("");
  if (animateNew) {
    const first = $("#eventFeed .event");
    if (first && !first.dataset.seen) first.classList.add("fresh");
  }
  $$("#eventFeed .event").forEach((el) => {
    el.addEventListener("click", () => openEventDecision(el.dataset.id));
  });
}

async function openEventDecision(eventId) {
  const decisions = await api("/api/agent/decisions?limit=50");
  const match = decisions.find((d) => d.event && d.event.id === eventId);
  if (!match) { toast("No agent decision recorded for that event yet.", "warn"); return; }
  state.activeDecision = match;
  renderDecision(match);
}

/* ---------------- templates / simulation ---------------- */
async function refreshTemplates() {
  const groups = await api("/api/agent/templates");
  state.templates = groups;
  $("#templates").innerHTML = groups.map((g) => `
    <div class="tpl-group">${esc(g.group)}</div>
    ${g.templates.map((t) => `
      <button class="tpl" data-key="${esc(t.key)}">
        <span class="t">${esc(t.label)}</span>
        <span class="d">${esc(t.description || t.title)}</span>
        <span class="i ${esc(t.importance)}">${esc(t.importance)}</span>
        <span class="tag" style="margin-left:6px">${esc(t.category)}</span>
      </button>`).join("")}`).join("");
  $$("#templates .tpl").forEach((btn) =>
    btn.addEventListener("click", () => simulate(btn.dataset.key, btn)));
}

async function simulate(key, btn) {
  if (state.polling) { toast("Agent is already working an event.", "warn"); return; }
  $$("#templates .tpl").forEach((b) => (b.disabled = true));
  $("#simState").textContent = "RUNNING";
  $("#simState").className = "badge warn";
  resetChain();
  try {
    const started = await api("/api/agent/simulate", {
      method: "POST", body: JSON.stringify({ template_key: key }),
    });
    state.activeDecision = null;
    pollDecision(started.decision_id, btn);
  } catch (err) {
    toast("Simulation failed: " + err.message, "err");
    finishSim(btn);
  }
}

function pollDecision(decisionId, btn) {
  let elapsed = 0;
  state.polling = setInterval(async () => {
    elapsed += 350;
    try {
      const run = await api(`/api/agent/decisions/${decisionId}`);
      state.activeDecision = run;
      renderDecision(run);
      if (run.status !== "running") {
        clearInterval(state.polling);
        state.polling = null;
        finishSim(btn);
        await Promise.all([refreshPortfolio(), refreshEvents(), refreshTrades(), refreshDecisions()]);
        announce(run);
      } else if (elapsed > 30000) {
        clearInterval(state.polling);
        state.polling = null;
        finishSim(btn);
        toast("Timed out waiting for the agent.", "err");
      }
    } catch (err) {
      clearInterval(state.polling);
      state.polling = null;
      finishSim(btn);
      toast("Polling failed: " + err.message, "err");
    }
  }, 350);
}

function finishSim(btn) {
  $$("#templates .tpl").forEach((b) => (b.disabled = false));
  $("#simState").textContent = "READY";
  $("#simState").className = "badge";
}

function announce(run) {
  const risk = run.risk ? run.risk.status : "UNKNOWN";
  if (risk === "APPROVED" || risk === "REDUCED") {
    toast(`PAPER TRADE EXECUTED - ${run.trades.length} fill(s) - risk ${risk}`, "ok");
  } else if (risk === "REJECTED") {
    toast(`Blocked by risk engine: ${(run.risk.reasons[0] || "no reason").slice(0, 90)}`, "err");
  } else {
    toast(`Decision ${run.status}`, "warn");
  }
}

/* ---------------- decision chain ---------------- */
function renderChainShell() {
  $("#chain").innerHTML = CHAIN_STAGES.map((s, i) => `
    <div class="step idle" data-stage="${s.key}">
      <div class="rail"><div class="dot">${s.n}</div>${i < CHAIN_STAGES.length - 1 ? '<div class="line"></div>' : ""}</div>
      <div class="step-body">
        <div class="row"><div class="step-title">${s.label}</div><div class="spacer"></div>
          <div class="step-dur"></div></div>
        <div class="step-detail">Waiting&hellip;</div>
      </div>
    </div>`).join("");
}

function resetChain() {
  $$("#chain .step").forEach((el) => {
    el.className = "step active";
    el.querySelector(".step-detail").textContent = "Working\u2026";
    el.querySelector(".step-dur").textContent = "";
  });
  const first = $("#chain .step");
  if (first) first.classList.add("active");
  $("#decisionStatus").innerHTML = `<span class="verdict RUNNING">RUNNING</span>`;
  $("#decisionDetail").innerHTML = "";
}

function stageEntry(run, key, also) {
  const wanted = [key, ...(also || [])];
  return (run.timeline || []).filter((t) => wanted.includes(t.stage));
}

function renderChain(run) {
  const done = new Set((run.timeline || []).map((t) => t.stage));
  CHAIN_STAGES.forEach((stage, index) => {
    const el = $(`#chain .step[data-stage="${stage.key}"]`);
    if (!el) return;
    const entries = stageEntry(run, stage.key, stage.also);
    const primary = entries[0];
    if (primary) {
      el.className = "step done " + (primary.status === "error" ? "error" : primary.status === "warning" ? "warn" : "");
      el.querySelector(".step-title").textContent = stage.label;
      const detail = entries.map((e) => e.detail).filter(Boolean).join(" \u2014 ");
      el.querySelector(".step-detail").textContent = primary.title + (detail ? ": " + detail : "");
      el.querySelector(".step-dur").textContent = primary.duration_ms ? primary.duration_ms + "ms" : "";
    } else {
      const reached = CHAIN_STAGES.slice(0, index).some((s) => done.has(s.key));
      el.className = "step " + (run.status === "running" && reached ? "active" : "idle");
      el.querySelector(".step-detail").textContent = run.status === "running" ? "Working\u2026" : "Waiting\u2026";
      el.querySelector(".step-dur").textContent = "";
    }
  });

  const verdict = run.status === "running" ? "RUNNING" : run.risk ? run.risk.status : "FAILED";
  $("#decisionStatus").innerHTML = `<span class="verdict ${verdict}">${verdict}</span>`;
}

/* ---------------- decision detail ---------------- */
function renderDecision(run) {
  state.activeDecision = run;
  renderChain(run);
  renderDecisionDetail(run);
  renderTimeline(run);
  renderExplain(run);
}

function renderDecisionDetail(run) {
  const parts = [];
  const ev = run.event || {};
  parts.push(`<div class="why"><h4>Event</h4><p><b>${esc(ev.title || "")}</b></p>
    <div class="meta">
      <span class="kv">source <b>${esc(ev.source || "")}</b></span>
      <span class="kv">category <b>${esc(ev.category || "")}</b></span>
      <span class="kv">importance <b>${esc((ev.importance || "").toUpperCase())}</b></span>
      <span class="kv">time <b>${esc(clock(ev.timestamp || ""))}</b></span>
    </div></div>`);

  const a = run.analysis;
  if (a) {
    const bars = (a.affected_assets || []).slice().sort((x, y) => y.impact_score - x.impact_score)
      .map((asset) => `<div class="impact-row">
        <span class="sym">${esc(asset.symbol)}</span>
        <span class="bar"><span class="${esc(asset.direction)}" style="width:${asset.impact_score}%"></span></span>
        <span class="score ${asset.direction === "positive" ? "pos" : asset.direction === "negative" ? "neg" : "neu"}">
          ${asset.direction === "positive" ? "+" : asset.direction === "negative" ? "-" : ""}${asset.impact_score}</span>
      </div>`).join("");
    const actions = (a.portfolio_actions || []).map((act) =>
      `<span class="tag ${act.action === "REDUCE" || act.action === "SELL" ? "" : "sym"}">
        ${esc(act.action)} ${esc(act.symbol)} ${Number(act.percentage).toFixed(0)}%</span>`).join(" ") ||
      `<span class="tag">NO CHANGE</span>`;
    parts.push(`<div class="section-label">Qwen interpretation &middot; ${esc(a.provider)} / ${esc(a.model)}</div>
      <div class="why" style="border-left-color:var(--cyan);background:#0b141c">
        <h4 style="color:var(--cyan)">Market impact</h4>
        <div class="meta" style="margin:0 0 9px">
          <span class="kv">type <b>${esc(a.event_type)}</b></span>
          <span class="kv">sentiment <b>${esc(a.sentiment)}</b></span>
          <span class="kv">regime <b>${esc(String(a.market_regime).replace("_", "-"))}</b></span>
          <span class="kv">confidence <b>${Math.round(a.confidence * 100)}%</b></span>
          <span class="kv">horizon <b>${esc(a.time_horizon)}</b></span>
          <span class="kv">action <b>${esc(a.recommended_action)}</b></span>
        </div>
        ${bars}
        <div class="section-label" style="margin-top:10px">Proposed portfolio actions (unvalidated)</div>
        <div class="row">${actions}</div>
        <p style="margin-top:9px">${esc(a.reasoning_summary)}</p>
      </div>`);
  }

  const risk = run.risk;
  if (risk) {
    const checks = Object.entries(risk.checks || {}).map(([name, result]) =>
      `<div class="check ${result}"><span class="name">${esc(name.replace(/_/g, " "))}</span>
        <span class="res">${result}</span></div>`).join("");
    const approved = (risk.approved_actions || []).map((act) =>
      `<span class="tag sym">${esc(act.action)} ${esc(act.symbol)} ${Number(act.percentage).toFixed(1)}%</span>`).join(" ") ||
      `<span class="tag">NONE</span>`;
    parts.push(`<div class="section-label">Risk engine &middot; deterministic</div>
      <div class="why" style="border-left-color:${risk.status === "APPROVED" ? "var(--green)" :
        risk.status === "REDUCED" ? "var(--amber)" : "var(--red)"};background:#0c1219">
        <div class="row"><span class="verdict ${risk.status}">${risk.status}</span>
          <span class="spacer"></span>
          <span class="kv">size scale <b>${Math.round((risk.scale_factor || 0) * 100)}%</b></span></div>
        <div class="risk-grid">${checks}</div>
        <div class="section-label" style="margin-top:10px">Approved for execution</div>
        <div class="row">${approved}</div>
        ${(risk.reasons || []).length ? `<ul class="reasons">${risk.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      </div>`);
  }

  if (run.trades && run.trades.length) {
    parts.push(`<div class="section-label">Execution &middot; PAPER</div>
      <table><thead><tr><th>Asset</th><th>Action</th><th>Qty</th><th>Fill</th><th>Notional</th><th>Slip</th></tr></thead>
      <tbody>${run.trades.map((t) => `<tr>
        <td class="sym">${esc(t.symbol)}</td>
        <td class="${t.side === "BUY" ? "pos" : "neg"}">${esc(t.action)}</td>
        <td>${num(t.quantity)}</td><td>${money(t.price)}</td>
        <td>${money(t.notional, 0)}</td><td>${(t.slippage * 100).toFixed(3)}%</td></tr>`).join("")}
      </tbody></table>`);
  } else if (risk) {
    parts.push(`<div class="empty">No paper trade executed for this decision.</div>`);
  }

  $("#decisionDetail").innerHTML = parts.join("");
}

/* ---------------- timeline ---------------- */
async function refreshDecisions() {
  state.decisions = await api("/api/agent/decisions?limit=25");
  const latest = state.decisions[0];
  $("#tlMeta").textContent = `${state.decisions.length} decisions`;
  if (latest && !state.activeDecision) renderDecision(latest);
  await refreshTrades();
}

function renderTimeline(run) {
  if (!run || !(run.timeline || []).length) {
    $("#timeline").innerHTML = `<div class="empty">No decisions yet.</div>`;
    return;
  }
  $("#timeline").innerHTML = `<div class="tl">${run.timeline.map((t) => `
    <div class="tl-item">
      <div class="tl-time">${clock(t.timestamp)}<br/><span style="color:#3f4d61">${t.duration_ms || 0}ms</span></div>
      <div class="tl-dot ${t.status === "error" ? "error" : t.status === "warning" ? "warning" : ""}"></div>
      <div class="tl-body">
        <div class="tl-title">${esc(t.title)}<span class="tl-stage">${esc(t.stage.replace(/_/g, " "))}</span></div>
        <div class="tl-detail">${esc(t.detail)}</div>
      </div>
    </div>`).join("")}</div>`;
}

function renderExplain(run) {
  if (!run || !run.explanation) { $("#explain").innerHTML = `<div class="empty">No explanation yet.</div>`; return; }
  const s = run.summary || {};
  $("#explain").innerHTML = `<div class="why"><h4>Why did Eventra do that?</h4>
    <p>${esc(run.explanation)}</p>
    <div class="meta">
      <span class="kv">decision <b>${esc(run.id)}</b></span>
      <span class="kv">risk <b>${esc(s.risk_status || "n/a")}</b></span>
      <span class="kv">fills <b>${s.trade_count ?? run.trades.length}</b></span>
      <span class="kv">llm <b>${esc(run.llm_provider)}</b></span>
      <span class="kv">mode <b>${esc(run.mode)}</b></span>
    </div></div>`;
}

async function refreshTrades() {
  const trades = await api("/api/portfolio/trades?limit=40");
  state.trades = trades;
  $("#trades tbody").innerHTML = trades.length ? trades.map((t) => `
    <tr><td>${clock(t.created_at)}</td>
      <td class="${t.side === "BUY" ? "pos" : "neg"}">${esc(t.action)}</td>
      <td class="sym">${esc(t.symbol)}</td><td>${num(t.quantity)}</td>
      <td>${money(t.price)}</td><td>${money(t.notional, 0)}</td>
      <td>${esc((t.reason || "").split(" - ")[0].slice(0, 26))}</td></tr>`).join("")
    : `<tr><td colspan="7" class="empty">No trades yet.</td></tr>`;
}

/* ---------------- controls ---------------- */
$("#killSwitch").addEventListener("click", async () => {
  const next = !state.killSwitch;
  try {
    await api("/api/system/kill-switch", { method: "POST", body: JSON.stringify({ engaged: next }) });
    state.killSwitch = next;
    await refreshStatus();
    toast(next ? "KILL SWITCH ARMED - all trading halted." : "Kill switch released - agent resumed.",
      next ? "err" : "ok");
  } catch (err) { toast("Kill switch error: " + err.message, "err"); }
});

$("#resetBtn").addEventListener("click", async () => {
  if (!window.confirm("Reset the simulated portfolio, events and decision history?")) return;

  const token = window.prompt("Enter the admin token:");
  if (!token) return;

  try {
    await api("/api/system/reset", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": token,
      },
      body: "{}",
    });

    state.activeDecision = null;
    renderChainShell();
    $("#decisionDetail").innerHTML = "";
    $("#timeline").innerHTML = `<div class="empty">No decisions yet.</div>`;
    $("#explain").innerHTML = `<div class="empty">Run an event to generate an explanation.</div>`;
    await Promise.all([refreshStatus(), refreshPortfolio(), refreshEvents(), refreshDecisions()]);
    toast("Demo state reset.", "ok");
  } catch (err) {
    toast("Reset failed: " + err.message, "err");
  }
});

$("#syncBtn").addEventListener("click", async () => {
  const token = window.prompt("Enter the admin token:");
  if (!token) return;

  try {
    const result = await api("/api/events/sync?limit=40", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": token,
      },
      body: "{}",
    });

    await refreshEvents();
    toast(`Ingested ${result.ingested} new event(s) from the provider.`, "ok");
  } catch (err) {
    toast("Sync failed: " + err.message, "err");
  }
});

$("#analyzeBtn").addEventListener("click", async () => {
  const token = window.prompt("Enter the admin token to analyze pending events:");
  if (!token) return;

  $("#analyzeBtn").disabled = true;
  $("#analyzeBtn").textContent = "ANALYZING...";

  try {
    const result = await api("/api/system/analyze-pending", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Token": token,
      },
      body: "{}",
    });

    await Promise.all([refreshEvents(), refreshDecisions(), refreshPortfolio()]);
    
    if (result.analyzed > 0) {
      toast(`Analyzed ${result.analyzed} event(s) with Qwen. ${result.failed > 0 ? result.failed + ' failed.' : ''}`, "ok");
    } else if (result.total_pending === 0) {
      toast("No pending events to analyze.", "warn");
    } else {
      toast(`Analysis complete. ${result.failed} failed.`, "warn");
    }
  } catch (err) {
    toast("Analysis failed: " + err.message, "err");
  } finally {
    $("#analyzeBtn").disabled = false;
    $("#analyzeBtn").textContent = "ANALYZE PENDING";
  }
});

// --- 7x24 Market Status ---
async function loadMarketStatus() {
  try {
    const data = await api("/api/market/weekend");
    const statusEl = $("#marketStatus");
    const contentEl = $("#weekendStatus");
    if (!statusEl || !contentEl) return;
    
    statusEl.textContent = data.market_status;
    statusEl.className = "badge " + (data.is_market_open ? "ok" : "warn");
    
    let html = `
      <div class="market-info">
        <div class="info-row">
          <span class="info-label">Day:</span>
          <span class="info-value">${data.day_of_week}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Traditional Market:</span>
          <span class="info-value ${data.traditional_market === 'OPEN' ? 'pos' : 'neg'}">${data.traditional_market}</span>
        </div>
        <div class="info-row">
          <span class="info-label">rToken Market:</span>
          <span class="info-value ${data.trading_implications.rToken_active ? 'pos' : 'neu'}">${data.trading_implications.rToken_active ? 'ACTIVE' : 'INACTIVE'}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Gap Risk:</span>
          <span class="info-value ${data.trading_implications.gap_risk === 'high' ? 'neg' : data.trading_implications.gap_risk === 'medium' ? 'warn' : 'neu'}">${data.trading_implications.gap_risk.toUpperCase()}</span>
        </div>
      </div>
    `;
    
    if (data.is_weekend || data.is_after_hours) {
      html += `
        <div class="alert-box weekend-alert">
          <div class="alert-icon">⚡</div>
          <div class="alert-text">
            <strong>7x24 Trading Active</strong><br>
            <small>rTokens are trading while traditional markets are closed. Event-driven opportunities may exist.</small>
          </div>
        </div>
      `;
    }
    
    contentEl.innerHTML = html;
  } catch (err) {
    $("#weekendStatus").innerHTML = `<div class="empty">Failed to load market status</div>`;
  }
}

// --- rToken Arbitrage ---
async function loadArbitrage() {
  try {
    const data = await api("/api/market/arbitrage");
    const panel = $("#arbitragePanel");
    
    if (!data.opportunities || data.opportunities.length === 0) {
      panel.innerHTML = `<div class="empty">No arbitrage opportunities detected</div>`;
      return;
    }
    
    let html = '<div class="arb-list">';
    for (const opp of data.opportunities.slice(0, 5)) {
      const premiumClass = opp.premium_pct > 0 ? 'pos' : 'neg';
      const premiumSign = opp.premium_pct > 0 ? '+' : '';
      html += `
        <div class="arb-item">
          <div class="arb-header">
            <span class="arb-symbol">${opp.rtoken} → ${opp.underlying}</span>
            <span class="arb-premium ${premiumClass}">${premiumSign}${opp.premium_pct.toFixed(2)}%</span>
          </div>
          <div class="arb-details">
            <span>rToken: $${opp.rtoken_price.toFixed(2)}</span>
            <span>Underlying: $${opp.underlying_price.toFixed(2)}</span>
          </div>
          <div class="arb-action">${opp.action}</div>
        </div>
      `;
    }
    html += '</div>';
    panel.innerHTML = html;
  } catch (err) {
    $("#arbitragePanel").innerHTML = `<div class="empty">Failed to load arbitrage data</div>`;
  }
}

// --- Performance Metrics ---
async function loadMetrics() {
  try {
    const data = await api("/api/metrics");
    const panel = $("#metricsPanel");
    const meta = $("#metricsMeta");
    
    meta.textContent = `${data.total_trades} trades`;
    
    const sharpeClass = data.sharpe_ratio > 0 ? 'pos' : data.sharpe_ratio < 0 ? 'neg' : 'neu';
    const sortinoClass = data.sortino_ratio > 0 ? 'pos' : data.sortino_ratio < 0 ? 'neg' : 'neu';
    const drawdownClass = data.max_drawdown_pct < -5 ? 'neg' : data.max_drawdown_pct < -2 ? 'warn' : 'neu';
    const winRateClass = data.win_rate > 60 ? 'pos' : data.win_rate < 40 ? 'neg' : 'neu';
    
    let html = `
      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-label">Sharpe Ratio</div>
          <div class="metric-value ${sharpeClass}">${data.sharpe_ratio.toFixed(2)}</div>
          <div class="metric-desc">Risk-adjusted return</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Sortino Ratio</div>
          <div class="metric-value ${sortinoClass}">${data.sortino_ratio.toFixed(2)}</div>
          <div class="metric-desc">Downside risk adjusted</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Max Drawdown</div>
          <div class="metric-value ${drawdownClass}">${data.max_drawdown_pct.toFixed(2)}%</div>
          <div class="metric-desc">Largest peak-to-trough</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Win Rate</div>
          <div class="metric-value ${winRateClass}">${data.win_rate.toFixed(1)}%</div>
          <div class="metric-desc">${data.winning_trades}/${data.total_trades} trades</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Profit Factor</div>
          <div class="metric-value ${data.profit_factor > 1.5 ? 'pos' : data.profit_factor > 1 ? 'neu' : 'neg'}">${data.profit_factor.toFixed(2)}</div>
          <div class="metric-desc">Gross profit/loss ratio</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Total Fees</div>
          <div class="metric-value">$${data.total_fees.toFixed(2)}</div>
          <div class="metric-desc">Transaction costs</div>
        </div>
      </div>
    `;
    
    panel.innerHTML = html;
  } catch (err) {
    $("#metricsPanel").innerHTML = `<div class="empty">Failed to load metrics</div>`;
  }
}

// Load Bitget live market data
async function loadBitgetMarketData() {
  try {
    const data = await api('/api/market/live');
    updateCryptoPricesTable(data.prices);
    updateFundingRatesTable(data.funding_rates);
    const badge = document.getElementById('bitgetBadge');
    if (badge) { badge.textContent = 'LIVE'; badge.className = 'badge ok'; }
  } catch (err) {
    console.error('Failed to load Bitget market data:', err);
    const badge = document.getElementById('bitgetBadge');
    if (badge) { badge.textContent = 'OFFLINE'; badge.className = 'badge err'; }
  }
}

function updateCryptoPricesTable(prices) {
  const tbody = document.querySelector('#cryptoPrices tbody');
  if (!tbody) return;
  if (!prices || Object.keys(prices).length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No price data available</td></tr>';
    return;
  }

  const rows = Object.entries(prices).map(([symbol, data]) => {
    const changeClass = data.change_24h >= 0 ? 'pos' : 'neg';
    const changeSign = data.change_24h >= 0 ? '+' : '';
    const volume = (data.quote_volume_24h / 1e6).toFixed(2);
    
    return `
      <tr>
        <td><strong>${symbol}</strong></td>
        <td>$${data.price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
        <td class="${changeClass}">${changeSign}${(data.change_24h * 100).toFixed(2)}%</td>
        <td>$${volume}M</td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = rows;
}

function updateFundingRatesTable(rates) {
  const tbody = document.querySelector('#fundingRates tbody');
  if (!tbody) return;
  if (!rates || Object.keys(rates).length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty">No funding rate data available</td></tr>';
    return;
  }

  const rows = Object.entries(rates).map(([symbol, data]) => {
    const rate = (data.funding_rate * 100).toFixed(4);
    const annualized = (data.funding_rate * 3 * 365 * 100).toFixed(2); // 8h intervals = 3 per day
    const rateClass = data.funding_rate >= 0 ? 'pos' : 'neg';
    
    return `
      <tr>
        <td><strong>${symbol}</strong></td>
        <td class="${rateClass}">${rate}%</td>
        <td class="${rateClass}">${annualized}%</td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = rows;
}

boot();
