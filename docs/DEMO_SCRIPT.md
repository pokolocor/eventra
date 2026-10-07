# Eventra — Demo & Pitch Script

> **Eventra — From Events to Execution.** An autonomous, event-driven trading agent.
> Market-moving events in → Qwen interprets → deterministic risk engine gates → paper trade out.

This doc gives you a tight pitch, a step-by-step live demo, talking points, and a judge Q&A.
Everything below runs in **Demo Mode** (no API key, no network) so it works anywhere.

---

## 1. The 60-second pitch

> "Markets don't move on charts — they move on **events**. A Fed decision, a CPI print, an
> earnings beat. Traders who react fastest to those events win.
>
> **Eventra** is an autonomous agent that watches for market-moving events, uses **Qwen** to
> interpret each one — what it means, which assets it hits, how confident we are — then proposes
> a trade.
>
> But here's the important part: **Qwen never touches the money.** Every proposal goes through a
> separate, deterministic **risk engine** that enforces position limits, exposure caps, liquidity,
> volatility and a global kill switch. Only what survives the risk engine becomes a paper trade.
>
> The whole chain — event, interpretation, signal, risk check, execution, portfolio update — is
> shown live on the dashboard with a human-readable explanation for every single decision.
>
> It's **paper trading only**, fully explainable, and safe by design."

---

## 2. The 3-minute live demo

Open `http://127.0.0.1:8000/ui/` (or `python backend/run.py` to start it).

### Step 0 — Set the stage (10s)
Point at the top bar.
> "This is a live autonomous agent. Top-right: **PAPER / DEMO** badge, the **LLM provider**, the
> data store, a **LIVE** indicator, and a global **KILL SWITCH**. Everything is simulated — no real
> money, no real orders."

### Step 1 — Point at the seeded world (15s)
Gesture to the **Live Event Feed** (left) and **Positions** table (bottom).
> "The feed is already populated with realistic events — Fed commentary, earnings, crypto flows.
> The book holds 9 positions across equities, ETFs, bonds, gold and crypto, worth about $1M."

### Step 2 — Fire the flagship event (60s)
Click **Simulate Event → "Fed rate decision – hawkish hold"**.
Narrate as the chain lights up, one stage at a time:

> "A new event arrives: *the Fed holds rates but signals fewer cuts than expected.* Watch the
> **Agent Decision Center** on the right."
>
> 1. **EVENT DETECTED** — "Eventra ingested it and tagged it `central_bank`, importance CRITICAL."
> 2. **QWEN ANALYSIS** — "Qwen classifies it: monetary policy, **bearish**, **risk-off** regime,
>    **87% confidence**, 1–5 day horizon."
> 3. **MARKET IMPACT** — "It scores the affected assets — QQQ negative 82, IWM negative 74, TLT
>    negative 70, JPM positive 52 — and proposes: reduce QQQ 10%, reduce BTC 5%, reduce IWM 6%,
>    increase TLT 5%."
> 4. **RISK CHECK** — "This is the gate. Ten deterministic checks — kill switch, confidence, daily
>    loss, duplicate signal, liquidity, volatility, position limit, exposure, trade size, portfolio
>    rules. All **PASS** → **APPROVED**."
> 5. **EXECUTION** — "**PAPER TRADE EXECUTED**, 4 fills."

Then point down:
> "The **Decision Timeline** shows the same chain chronologically, and the **Explainability** panel
> answers the question every risk officer asks: *why did Eventra do that?*"

### Step 3 — Show the risk engine saying NO (40s)
Click **Simulate Event → "Illiquid micro-cap pump (risk engine demo)"**.
> "Now the safety story. This event proposes buying an illiquid micro-cap. Qwen is confident — but
> the **risk engine REJECTS it**: liquidity check fails. **No trade.** The LLM can be wrong or
> overconfident; the risk engine is the backstop. That's the whole point."

Optionally also show **"Unconfirmed rumour"** (rejected by the confidence gate) and the **KILL
SWITCH** (engage it, fire any event → blocked; disengage).

### Step 4 — Close (15s)
> "So: events in, Qwen interprets, a deterministic risk engine gates, paper trades out — every step
> visible, every decision explained, and nothing can bypass the risk controls. **Eventra: from
> events to execution.**"

---

## 3. Architecture talking points (if judges go deep)

- **Pipeline:** `Event → Qwen interpretation → Market impact → Signal → Risk engine → Paper trade → Portfolio → Timeline`. Each stage is a distinct service; the orchestrator stitches them and records an audit trail.
- **Qwen is the brain, the risk engine is the brake.** Qwen returns *structured JSON* (event type, sentiment, regime, confidence, per-asset impact scores, proposed actions). The backend **validates that JSON with Pydantic** before anything else happens — malformed output is repaired once, then rejected loudly. Qwen output **never** bypasses risk controls.
- **Deterministic risk engine** (`risk_engine.py`): kill switch → confidence threshold → daily-loss halt → duplicate-signal cooldown → liquidity → volatility → position limit → gross exposure → max trade size → portfolio rules. Returns `APPROVED` / `REDUCED` / `REJECTED` with per-check PASS/WARN/FAIL and reasons. A failing check can never be reported as APPROVED.
- **Provider abstraction:** news and market data sit behind interfaces, so a real feed (Reuters/Bloomberg/Alpha Vantage) or broker can be swapped in without touching the agent.
- **Persistence:** SQLAlchemy ORM targeting **PostgreSQL** (via `docker-compose.yml`); a zero-dependency JSON store is the offline default so the demo runs with nothing installed.
- **Explainability:** every decision carries a plain-English sentence built from the actual pipeline artefacts — not a canned string.
- **Paper trading only:** the execution service simulates fills with slippage and fees; there is no path to a real broker.

## 4. Judge Q&A

**Q: Is this real money?**
A: No — paper trading only. The execution layer is a simulator; there is no broker connection and no way to send a real order.

**Q: What stops the LLM from doing something reckless?**
A: Three layers. (1) Qwen output is schema-validated before use. (2) A separate deterministic risk engine enforces limits and can REJECT or REDUCE. (3) A global kill switch halts all trading instantly. The LLM proposes; the risk engine disposes.

**Q: What if Qwen returns garbage?**
A: The service extracts JSON, validates it against a Pydantic model, attempts one repair, and if it still fails the decision is recorded as an error with a clear explanation — the portfolio is untouched.

**Q: Why not let the LLM size the trade directly?**
A: Because sizing is where blow-ups happen. Qwen gives a *direction and a percentage intent*; the risk engine translates that into an actual size subject to position, exposure, liquidity, volatility and cash limits.

**Q: How is this different from a chatbot?**
A: It's an autonomous event-to-execution system with a hard safety gate and full auditability — not a conversational assistant. The chat surface doesn't exist; the product is the pipeline and the dashboard.

**Q: Can it connect to real data?**
A: Yes — the news and market-data providers are abstracted. Drop in a real feed and set `QWEN_API_KEY` and it runs the same pipeline against live events.

## 5. Safety & guardrails (say these out loud)

- API keys come **only** from environment variables (`QWEN_API_KEY`) — never hard-coded, never sent to the frontend.
- All LLM output is validated; malformed responses are handled, not trusted.
- LLM output can never bypass the risk engine.
- Global emergency **kill switch** halts every trade.
- **Every** agent decision is logged to an audit trail.
- Clearly labelled **PAPER / DEMO** everywhere.

## 6. Fallback plan (no key / no network)

- Demo Mode is the default: deterministic mock events + a clearly-stamped `demo-mock` Qwen provider. The pipeline, risk engine, portfolio and dashboard behave identically.
- If you *do* have a key: `set QWEN_API_KEY=...` (Windows) or `export QWEN_API_KEY=...` (macOS/Linux), restart `python backend/run.py`, and the **LLM provider** badge flips from `demo` to the real model — same demo, real inference.
- If the server won't start: `python backend/run.py` auto-falls back from FastAPI to the zero-dependency stdlib server with the identical API and UI.

---

*Tip: rehearse the 3-minute demo twice. The hawkish-Fed run (APPROVED) and the illiquid-micro-cap run (REJECTED) together tell the entire story: the agent acts, and the agent refuses — both for explainable reasons.*
