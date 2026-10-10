# Eventra

### From Events to Execution

Eventra is an autonomous, event-driven trading agent. It watches market-moving
events — central-bank decisions, inflation prints, earnings, policy shifts,
geopolitics, crypto regulation — and turns each one into a **validated, risk-gated
paper trade**, with a full audit trail of *why*.

```
EVENT  →  QWEN INTERPRETATION  →  MARKET IMPACT  →  TRADING DECISION
       →  RISK ENGINE  →  PAPER EXECUTION  →  PORTFOLIO UPDATE
```

The LLM proposes. A **deterministic risk engine** disposes. Qwen output never
touches the portfolio directly — it is re-sized, capped, or discarded by hard
numeric limits before anything is executed.

> **PAPER / DEMO ONLY.** Eventra contains no live-broker code path. Setting
> `EVENTRA_PAPER_TRADING_ONLY=false` does not enable real trading; the execution
> service raises instead.

---

## Quick start

### Option A — zero install (offline demo)

Requires only **Python 3.10+**. No `pip install`, no database, no API key.

```bash
python backend/run.py
# → API      http://127.0.0.1:8000/api
# → Terminal http://127.0.0.1:8000/
```

If FastAPI/uvicorn are missing, Eventra automatically serves the identical JSON
API from a standard-library server (`backend/dev_server.py`) and stores state in
`backend/data/eventra_state.json`. The bundled dark-theme trading terminal is
served at `/`.

### Option B — full stack (FastAPI + PostgreSQL + Next.js)

```bash
# 1. backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env                # then set QWEN_API_KEY
docker compose up -d db                             # PostgreSQL 16 on :5432
uvicorn backend.main:app --reload --port 8000

# 2. frontend
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                                         # http://localhost:3000
```

The Next.js dev server proxies `/api/*` to the backend (see
`frontend/next.config.mjs`), so the browser never makes a cross-origin call and
never sees a secret.

### Bitget Demo Integration

Eventra integrates with **Bitget Demo Trading** for the Bitget AI Base Camp Hackathon.
When configured, all paper trades are mirrored to your Bitget Demo account.

```bash
# Add to backend/.env
BITGET_API_KEY=your_bitget_api_key
BITGET_API_SECRET=your_bitget_api_secret
BITGET_PASSPHRASE=your_bitget_passphrase
```

To get Bitget Demo API keys:
1. Log in to [Bitget](https://www.bitget.com/)
2. Go to **API Management** → Create API Key
3. Select **Demo Trading** mode (not live trading)
4. Copy the API Key, Secret, and Passphrase to your `.env` file

The dashboard shows a **BITGET DEMO** badge in the top bar when configured.
All trades executed by Eventra are automatically mirrored to your Bitget Demo account.

### Tests

```bash
python backend/run_tests.py      # uses pytest when installed, built-in runner otherwise
# or
pytest backend/tests -q
```

81 tests cover Qwen response validation, malformed/LLM-failure handling, every
risk limit, position sizing, event classification, portfolio maths, execution,
rejections and the kill switch.

---

## The demo, in ninety seconds

> Presenting at a hackathon? There is a word-for-word 60-second pitch, a timed 3-minute live-demo script and a judge Q&A in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

1. Open the dashboard. The book is already seeded: nine positions, a 60-point
   equity curve and twelve historical events.
2. In **Simulate Event**, click **Fed rate decision — hawkish hold**.
3. Watch the **Agent Decision Center** light up stage by stage:
   `EVENT DETECTED → QWEN ANALYSIS → MARKET IMPACT → RISK CHECK → EXECUTION`.
4. Qwen classifies it *hawkish / risk-off* at **87% confidence**, scores seven
   assets, and proposes `REDUCE QQQ 10% · REDUCE BTC 5% · REDUCE IWM 6% · INCREASE TLT 5%`.
5. The risk engine returns **APPROVED** with ten PASS checks; four paper fills land.
6. The **Decision Timeline**, **Positions**, **Portfolio Value** chart and KPI
   strip all update. **Explainability** answers *"Why did Eventra reduce QQQ?"*
7. Now click **Illiquid micro-cap pump** → the risk engine **REJECTS** it on the
   liquidity floor. Click **Unconfirmed rumour** → **REJECTED** on the 60%
   confidence gate. Arm the **KILL SWITCH** → everything halts.

That contrast — an agent that acts *and* refuses — is the point of the product.

---

## Architecture

```
eventra/
├── backend/
│   ├── main.py                  # FastAPI app (production entry)
│   ├── run.py                   # launcher: FastAPI if installed, else stdlib
│   ├── dev_server.py            # zero-dependency HTTP server, same JSON API
│   ├── run_tests.py             # pytest-or-builtin test runner
│   ├── config.py                # env-driven settings + RiskLimits
│   ├── api/
│   │   ├── handlers.py          # transport-agnostic controllers (single source of truth)
│   │   ├── deps.py
│   │   ├── routes_agent.py      # /api/agent/*
│   │   ├── routes_events.py     # /api/events/*
│   │   ├── routes_portfolio.py  # /api/portfolio/*
│   │   └── routes_system.py     # /api/system/*, /api/market/*, /api/health
│   ├── services/
│   │   ├── qwen_service.py      # Qwen client + JSON extraction + validation + retries
│   │   ├── demo_llm.py          # Demo Mode mock interpreter (clearly separated)
│   │   ├── event_service.py     # ingestion, normalisation, simulation
│   │   ├── risk_engine.py       # deterministic gate: the only authoriser of trades
│   │   ├── portfolio_service.py # paper book: fills, average cost, PnL, exposure
│   │   ├── execution_service.py # risk-approved actions -> simulated fills
│   │   ├── agent_orchestrator.py# the pipeline + timeline + audit trail
│   │   ├── explainability.py    # human-readable "why"
│   │   ├── registry.py          # composition root
│   │   └── providers/
│   │       ├── news.py          # NewsProvider ABC + demo + HTTP reference impl
│   │       ├── market_data.py   # MarketDataProvider ABC + deterministic sim
│   │       └── event_templates.py # 12 simulation templates + seeded history
│   ├── models/domain.py         # Pydantic domain types and enums
│   ├── schemas/api.py           # HTTP request/response schemas
│   ├── database/
│   │   ├── orm.py               # SQLAlchemy models (PostgreSQL / SQLite)
│   │   ├── repository.py        # Repository ABC, SqlRepository, JsonFileRepository
│   │   ├── session.py           # engine + session factory
│   │   ├── state.py             # PortfolioState / SystemState
│   │   └── seed.py              # demo book + event history
│   ├── static/                  # bundled dark-theme demo terminal
│   └── tests/                   # 81 tests
├── frontend/                    # Next.js 14 + TypeScript + Tailwind + Recharts
│   └── src/{app,components,hooks,lib}
├── scripts/                     # start-backend / start-frontend / test
└── docker-compose.yml           # PostgreSQL 16 + API
```

Both servers delegate to `backend/api/handlers.py`, so the FastAPI app and the
stdlib dev server can never drift apart.

### Swapping in real data

Every external dependency sits behind an interface:

| Concern | Interface | Demo implementation | To go live |
| --- | --- | --- | --- |
| News / events | `NewsProvider.fetch_events()` | `DemoNewsProvider` (seeded) | implement `HttpNewsProvider._map_item` for Benzinga, Polygon, NewsAPI, Finnhub or RSS |
| Prices / liquidity / vol | `MarketDataProvider` | `DemoMarketDataProvider` (seeded walk) | implement `quote()`, `history()`, `advance_tick()` against your vendor |
| LLM | `analyze_event(event) -> QwenAnalysis` | `DemoLLMService` | already live: set `QWEN_API_KEY` |
| Persistence | `Repository` | `JsonFileRepository` | `SqlRepository` + `DATABASE_URL` |
| Execution | `ExecutionService` | paper fills with slippage/fees | add a broker adapter; keep the risk engine in front of it |

---

## How Qwen is used

`backend/services/qwen_service.py` is the only place that talks to the model.

1. **Prompt.** A system prompt fixes the role ("you analyse, you never place
   orders") and the exact JSON schema. The user message is the normalised event
   (timestamp, title, source, category, importance, summary, affected assets, raw
   payload).
2. **Call.** OpenAI-compatible `POST {QWEN_BASE_URL}/chat/completions` with
   `model=QWEN_MODEL`, `temperature=0.2`, `response_format={"type":"json_object"}`,
   and `Authorization: Bearer $QWEN_API_KEY`. Implemented on `urllib` so the
   service has no third-party HTTP dependency.
3. **Extract.** `extract_json()` strips markdown fences and surrounding prose and
   isolates the first JSON object.
4. **Validate.** The object is parsed into `QwenAnalysis` (Pydantic): enums are
   checked, `confidence` is coerced from `87`/`"87%"`/`0.87` into `0..1`,
   `impact_score` accepts 0-100 or 0-1 floats, action strings are normalised
   (`"trim"` → `REDUCE`), non-actionable `HOLD`/zero-size proposals are dropped.
5. **Repair.** On a validation failure the errors are sent back to Qwen once
   (up to `QWEN_MAX_RETRIES`) with a repair instruction.
6. **Fail loudly.** Transport errors raise `QwenAPIError`; persistent schema
   failures raise `QwenValidationError` and the decision is marked `failed`.
   A configured-but-broken Qwen is **never** silently replaced with mock data.

The API key comes only from the environment (`QWEN_API_KEY`, optionally via
`backend/.env`). It is never referenced by frontend code and never returned by
any endpoint — `/api/system/status` reports only whether a key is configured.

### Demo Mode

`backend/services/demo_llm.py` is a separate module implementing the same
`analyze_event()` contract. It is used **only** when no `QWEN_API_KEY` exists,
and every response is stamped `provider="demo-mock"` with a `raw_output` note.
The dashboard shows a `LLM DEMO MOCK` badge and a `PAPER / DEMO` banner so no one
can mistake it for real model output.

### Response schema

```json
{
  "event_type": "macro",
  "sentiment": "bearish",
  "market_regime": "risk_off",
  "confidence": 0.87,
  "affected_assets": [
    { "symbol": "QQQ", "direction": "negative", "impact_score": 82 },
    { "symbol": "TLT", "direction": "positive", "impact_score": 68 }
  ],
  "time_horizon": "1-5 days",
  "recommended_action": "reduce_risk",
  "portfolio_actions": [
    { "symbol": "QQQ", "action": "reduce", "percentage": 10 }
  ],
  "reasoning_summary": "Brief explanation of the market interpretation."
}
```

---

## Risk controls

`backend/services/risk_engine.py` is deterministic, side-effect free and contains
no LLM call. It returns `APPROVED`, `REDUCED` or `REJECTED` plus a per-check
verdict and human-readable reasons.

| Check | Rule | On breach |
| --- | --- | --- |
| `kill_switch` | Global emergency stop engaged | **REJECT** everything |
| `confidence_threshold` | `confidence >= EVENTRA_MIN_CONFIDENCE` (0.60) | **REJECT** |
| `daily_loss_limit` | Session PnL > `-EVENTRA_MAX_DAILY_LOSS_PCT` (-4%) | **REJECT** |
| `duplicate_signal` | Same symbol+direction within 30 min cooldown | drop action; **REJECT** if all are duplicates |
| `liquidity` | ADV ≥ $250m and trade ≤ 2% of ADV | drop, or **REDUCE** to the participation cap |
| `volatility` | Annualised vol ≤ 90% | drop the action |
| `position_limit` | Post-trade weight ≤ 25% of the book | **REDUCE** to the headroom |
| `portfolio_exposure` | Projected gross exposure ≤ 90% | **REDUCE** new buys proportionally |
| `max_trade_size` | ≤ $150k and ≤ 12% of portfolio value | **REDUCE** |
| `portfolio_rules` | Instrument exists, exit requires a position, buys fully funded by cash, ≤ 6 actions | drop / **REDUCE** |

Example verdict:

```json
{
  "status": "APPROVED",
  "checks": {
    "kill_switch": "PASS", "confidence_threshold": "PASS", "daily_loss_limit": "PASS",
    "duplicate_signal": "PASS", "liquidity": "PASS", "volatility": "PASS",
    "position_limit": "PASS", "portfolio_exposure": "PASS", "max_trade_size": "PASS",
    "portfolio_rules": "PASS"
  },
  "reasons": [],
  "scale_factor": 1.0,
  "approved_actions": [{ "symbol": "QQQ", "action": "REDUCE", "percentage": 10 }]
}
```

Every limit is an environment variable (`EVENTRA_*`), loaded once into
`RiskLimits`. The LLM cannot see or modify them.

---

## Portfolio simulator

A paper book seeded with $1,000,000 (≈65% invested across QQQ, SPY, BTC, NVDA,
TLT, GLD, MSFT, IWM, JPM). It tracks cash, positions with average-cost entries,
realised and unrealised PnL, gross exposure, per-position agent conviction, an
equity curve and a full trade blotter. Supported actions: `BUY`, `SELL`,
`INCREASE`, `REDUCE`, `HOLD`, `HEDGE`. Fills include a participation-based
slippage model and a 0.5bp fee. There is no margin: buys must be funded by cash.

---

## Dashboard

| Section | What it shows |
| --- | --- |
| **Portfolio overview** | Value, today's PnL, total PnL, gross exposure, realised PnL |
| **Live Event Feed** | Event cards: title, time, source, category, importance, affected assets, Qwen analysis status |
| **Agent Decision Center** | The five-stage chain with live status, Qwen interpretation, impact bars, risk-check grid, approved actions, fills |
| **Portfolio chart** | Equity curve with the starting-balance baseline and hover readout |
| **Position table** | Asset, qty, entry, last, PnL, weight, agent conviction |
| **Decision Timeline** | Chronological record: event detected → Qwen analysis → signal → risk validation → trade executed → portfolio updated, each with duration |
| **Explainability** | "Why did Eventra do that?" plus the paper trade blotter |
| **Simulate Event** | Twelve templates across central bank, macro data, earnings, commodities, geopolitics, crypto and two deliberate stress tests |

Two UIs ship with the project:

* `frontend/` — the production **Next.js + TypeScript + Tailwind + Recharts** app.
* `backend/static/` — a bundled zero-build terminal served by the backend at `/`,
  which is what makes the project demoable with no `npm install`. Same API, same
  design language.

---

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness, mode, LLM provider, kill-switch state |
| GET | `/api/system/status` | Full configuration (redacted), limits, counters |
| POST | `/api/system/kill-switch` | `{"engaged": true|false}` — global emergency stop |
| POST | `/api/system/reset` | Re-seed the demo book, events and history |
| GET | `/api/system/audit` | Every agent decision and operator action |
| GET | `/api/market/quotes` | Simulated universe: price, change, vol, ADV |
| GET | `/api/events` | Event feed with per-event analysis status |
| POST | `/api/events` | Ingest an arbitrary event and run the pipeline |
| POST | `/api/events/sync` | Pull from the configured news provider |
| GET | `/api/agent/templates` | Simulation catalogue, grouped |
| POST | `/api/agent/simulate` | `{"template_key": "..."}` → `202 {decision_id}` (async) |
| POST | `/api/agent/run` | Same pipeline, synchronous, returns the full chain |
| GET | `/api/agent/decisions` | Decision history |
| GET | `/api/agent/decisions/{id}` | One decision, including partial state while `running` |
| GET | `/api/agent/explain/{symbol}` | "Why did Eventra touch this symbol?" |
| GET | `/api/portfolio` | Snapshot + enriched positions |
| GET | `/api/portfolio/history` | Equity curve |
| GET | `/api/portfolio/trades` | Blotter |
| GET | `/api/portfolio/positions` | Positions only |

`POST /api/agent/simulate` returns immediately and the pipeline runs in a worker
thread; poll `GET /api/agent/decisions/{id}` to watch the timeline build up stage
by stage. That is what drives the live "agent is working" animation.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `QWEN_API_KEY` | *(empty)* | Enables real Qwen analysis. Empty ⇒ Demo Mode |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible endpoint |
| `QWEN_MODEL` | `qwen-plus` | Any Qwen chat model (`qwen-max`, `qwen-turbo`, …) |
| `QWEN_TIMEOUT_SECONDS` / `QWEN_MAX_RETRIES` / `QWEN_TEMPERATURE` | `30` / `2` / `0.2` | Call behaviour |
| `EVENTRA_DEMO_MODE` | `true` | Allow the mock interpreter when no key exists |
| `EVENTRA_PAPER_TRADING_ONLY` | `true` | Hard-coded safety; disabling it disables execution entirely |
| `DATABASE_URL` | `postgresql+psycopg2://eventra:eventra@localhost:5432/eventra` | Any SQLAlchemy URL |
| `EVENTRA_STORE` | *auto* | Force `sql` or `json` |
| `EVENTRA_DATA_DIR` | `backend/data` | JSON store location |
| `EVENTRA_STARTING_BALANCE` | `1000000` | Seed capital |
| `EVENTRA_MAX_POSITION_WEIGHT_PCT` | `25` | Single-name cap |
| `EVENTRA_MAX_GROSS_EXPOSURE_PCT` | `90` | Book-level cap |
| `EVENTRA_MAX_TRADE_NOTIONAL` / `EVENTRA_MAX_SINGLE_TRADE_PCT` | `150000` / `12` | Per-trade caps |
| `EVENTRA_MAX_DAILY_LOSS_PCT` | `4` | Session stop |
| `EVENTRA_MIN_CONFIDENCE` | `0.60` | LLM confidence gate |
| `EVENTRA_MIN_ADV_USD` / `EVENTRA_MAX_TRADE_ADV_PCT` | `250000000` / `2` | Liquidity floor / participation |
| `EVENTRA_MAX_ANNUALIZED_VOL` | `0.90` | Volatility cap |
| `EVENTRA_DUPLICATE_COOLDOWN_MIN` | `30` | Repeat-signal window |
| `EVENTRA_MAX_ACTIONS_PER_DECISION` | `6` | Fan-out cap |
| `EVENTRA_NEWS_URL` / `EVENTRA_NEWS_TOKEN` / `EVENTRA_NEWS_ITEMS_KEY` | *(empty)* | Optional live news provider |
| `EVENTRA_CORS_ORIGINS` | `http://localhost:3000,…` | Comma-separated allow-list |

---

## Security

* **No secrets in the frontend.** The browser only calls same-origin `/api/*`;
  Next.js rewrites proxy to the backend. `QWEN_API_KEY` never leaves the server.
* **All LLM output is validated.** Strict Pydantic schemas, enum whitelists,
  range coercion and a repair retry. Unparseable output fails the decision.
* **The LLM cannot bypass risk.** `ExecutionService` only accepts a
  `RiskDecision`; `RiskStatus.REJECTED` means zero fills, and the kill switch is
  checked again at execution time.
* **Paper trading only.** No broker credentials exist anywhere in the repo.
* **Global kill switch.** One click halts every new trade across the system.
* **Full audit trail.** Every event, analysis, risk verdict, fill and operator
  action is written to `audit_log` and exposed at `/api/system/audit`.

---

## Testing

```bash
python backend/run_tests.py            # 81 tests, no dependencies required
python backend/run_tests.py risk       # filter by name
pytest backend/tests -q                # if pytest is installed
```

| File | Coverage |
| --- | --- |
| `tests/test_qwen_validation.py` | JSON extraction, fenced/prose replies, schema validation, enum rejection, malformed-then-repaired, persistent failure, missing key, HTTP errors |
| `tests/test_risk_engine.py` | Kill switch, confidence gate, liquidity, volatility, position limit, notional cap, exposure cap, duplicates, daily loss, unknown/unheld symbols |
| `tests/test_portfolio.py` | Average-cost accounting, realised PnL, exposure, insufficient cash/position, full exits, equity curve |
| `tests/test_execution.py` | Paper fills, blotter persistence, rejected/illiquid signals, kill switch, market advance, audit trail, live-trading guard |
| `tests/test_events.py` | Template integrity, seeding idempotency, simulation, normalisation, provider fallback |
| `tests/test_pipeline.py` | Stage ordering, analysis/signal/risk wiring, explainability, persistence, async runs, real-Qwen path, failure surfacing, multi-event solvency |

---

## Limitations and honest notes

* Prices, volume and volatility are simulated. The `MarketDataProvider` seam is
  where a live vendor plugs in.
* Demo Mode interpretations are deterministic mappings, not model reasoning.
  Set `QWEN_API_KEY` for the real thing.
* Position sizing is exposure-percentage based, not a Kelly/vol-targeting
  optimiser — deliberate, so the risk engine stays explainable on stage.
* No shorting or margin in the paper book; `HEDGE` is expressed as a long
  defensive allocation (TLT, GLD).

---

**Eventra — From Events to Execution.** Built for hackathon demonstration.
Paper trading only; nothing here is investment advice.
