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
async function boot() {
  renderChainShell();
  try {
    await refreshStatus();
    await Promise.all([refreshPortfolio(), refreshEvents(), refreshTemplates(), refreshDecisions()]);
    setConn(true);
  } catch (err) {
    setConn(false);
    toast("Cannot reach the Eventra API: " + err.message, "err");
  }
  setInterval(tick, 4000);
}

function setConn(ok) {
  const el = $("#connBadge");
  el.textContent = ok ? "LIVE" : "OFFLINE";
  el.className = "badge " + (ok ? "ok" : "err");
}

async function refreshStatus() {
  state.status = await api("/api/system/status");
  state.killSwitch = !!state.status.kill_switch;
  $("#modeBadge").textContent = state.status.mode || "PAPER / DEMO";
  const llm = state.status.llm || {};
  $("#llmBadge").textContent = "LLM " + (llm.provider === "qwen" ? "QWEN " + (llm.model || "") : "DEMO MOCK");
  $("#llmBadge").className = "badge " + (llm.provider === "qwen" ? "ok" : "warn");
  $("#dbBadge").textContent = "STORE " + String((state.status.database || {}).backend || "?").toUpperCase();
  const ks = $("#killSwitch");
  ks.classList.toggle("armed", state.killSwitch);
  ks.textContent = state.killSwitch ? "KILL SWITCH ARMED" : "KILL SWITCH";
}

async function tick() {
  try {
    await refreshStatus();
    await Promise.all([refreshPortfolio(), refreshEvents(), refreshTrades()]);
    setConn(true);
  } catch (_) { setConn(false); }
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
  $("#posMeta").textContent = `${p.positions.length} held`;
  $("#chartMeta").textContent = `${money(p.portfolio_value)}  ${pct(p.total_return_pct)}`;
}

function renderPositions(p) {
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
  $("#positions tbody").innerHTML = rows || `<tr><td colspan="7" class="empty">Flat book.</td></tr>`;
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
  if (!events.length) { $("#eventFeed").innerHTML = `<div class="empty">No events yet.</div>`; return; }
  $("#eventFeed").innerHTML = events.map((e) => {
    const decision = e.decision;
    const pill = decision
      ? `<span class="pill ${e.analysis_status}">${e.analysis_status.toUpperCase()}${
          decision.risk_status ? " &middot; " + decision.risk_status : ""}</span>`
      : `<span class="pill pending">AWAITING AGENT</span>`;
    const symbols = (e.affected_assets || []).slice(0, 5)
      .map((s) => `<span class="tag sym">${esc(s)}</span>`).join("");
    return `<div class="event imp-${esc(e.importance)}" data-id="${esc(e.id)}"
        data-template="${esc((e.raw || {}).template_key || "")}">
      <div class="event-top">${pill}<span class="tag time">${timeAgo(e.timestamp)}</span>
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
  try {
    await api("/api/system/reset", { method: "POST", body: "{}" });
    state.activeDecision = null;
    renderChainShell();
    $("#decisionDetail").innerHTML = "";
    $("#timeline").innerHTML = `<div class="empty">No decisions yet.</div>`;
    $("#explain").innerHTML = `<div class="empty">Run an event to generate an explanation.</div>`;
    await Promise.all([refreshStatus(), refreshPortfolio(), refreshEvents(), refreshDecisions()]);
    toast("Demo state reset.", "ok");
  } catch (err) { toast("Reset failed: " + err.message, "err"); }
});

$("#syncBtn").addEventListener("click", async () => {
  try {
    const result = await api("/api/events/sync?limit=40", { method: "POST", body: "{}" });
    await refreshEvents();
    toast(`Ingested ${result.ingested} new event(s) from the provider.`, "ok");
  } catch (err) { toast("Sync failed: " + err.message, "err"); }
});

boot();
