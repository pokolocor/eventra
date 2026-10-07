"""Seeded events + simulation templates.

Two distinct things live here:

* `SEEDED_EVENTS` - realistic historical events so the dashboard is populated
  the moment the app starts.
* `EVENT_TEMPLATES` - the catalogue behind the "Simulate Event" button.

Each template also carries an `expected_analysis` block. That block is ONLY used
by the clearly separated Demo Mode LLM (`backend/services/demo_llm.py`) when no
`QWEN_API_KEY` is configured. The real Qwen service never reads it: it always
calls the model and validates whatever comes back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class EventTemplate:
    key: str
    label: str
    group: str
    category: str
    importance: str
    source: str
    title: str
    summary: str
    affected_assets: Tuple[str, ...]
    expected_analysis: Dict[str, Any] = field(default_factory=dict)
    price_shocks: Dict[str, float] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "group": self.group,
            "category": self.category,
            "importance": self.importance,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "affected_assets": list(self.affected_assets),
            "description": self.description,
        }


EVENT_TEMPLATES: Dict[str, EventTemplate] = {
    t.key: t
    for t in [
        EventTemplate(
            key="fed_hawkish_hold",
            label="Fed rate decision - hawkish hold",
            group="Central bank",
            category="central_bank",
            importance="critical",
            source="Federal Reserve / Reuters",
            title="Federal Reserve keeps rates unchanged but signals fewer rate cuts than previously expected",
            summary=(
                "The FOMC held the target range at 4.75%-5.00%. The updated dot plot removed two of the four cuts "
                "markets had priced for next year and Chair Powell stressed that inflation progress has been "
                "'uneven'. Two-year yields jumped 14bp, the dollar index rallied and fed funds futures repriced the "
                "first cut from March to July."
            ),
            affected_assets=("QQQ", "SPY", "BTC", "TLT", "GLD", "IWM"),
            description="Hawkish surprise: growth assets de-rate, duration sells off, defensive bid.",
            expected_analysis={
                "event_type": "monetary_policy",
                "sentiment": "bearish",
                "market_regime": "risk_off",
                "confidence": 0.87,
                "time_horizon": "1-5 days",
                "recommended_action": "reduce_risk",
                "reasoning_summary": (
                    "Hawkish hold. Guidance implies fewer cuts than the market priced, raising the discount rate for "
                    "long-duration growth assets and pressuring risk appetite. Duration also suffers because the "
                    "terminal rate expectation moved higher."
                ),
                "impacts": [("QQQ", "negative", 82), ("SPY", "negative", 68), ("IWM", "negative", 74),
                            ("BTC", "negative", 61), ("TLT", "negative", 70), ("GLD", "neutral", 44),
                            ("JPM", "positive", 52)],
                "actions": [("QQQ", "REDUCE", 10), ("BTC", "REDUCE", 5), ("IWM", "REDUCE", 6),
                            ("TLT", "INCREASE", 5), ("GLD", "HOLD", 0)],
            },
            price_shocks={"QQQ": -0.018, "SPY": -0.012, "IWM": -0.021, "BTC": -0.026, "TLT": -0.009,
                          "GLD": 0.004, "JPM": 0.011},
        ),
        EventTemplate(
            key="cpi_surprise_low",
            label="CPI surprise - inflation cools",
            group="Macro data",
            category="inflation",
            importance="critical",
            source="Bureau of Labor Statistics",
            title="US CPI comes in significantly below expectations at 2.4% y/y",
            summary=(
                "Headline CPI rose 2.4% year over year versus 2.9% expected, with core CPI at 2.6% versus 3.0%. "
                "Shelter disinflation and falling used-vehicle prices drove the miss. Two-year yields fell 11bp and "
                "markets raised the probability of a cut at the next meeting to 78%."
            ),
            affected_assets=("QQQ", "SPY", "TLT", "IWM", "GLD", "BTC"),
            description="Dovish macro surprise: risk assets and duration rally together.",
            expected_analysis={
                "event_type": "inflation",
                "sentiment": "bullish",
                "market_regime": "risk_on",
                "confidence": 0.84,
                "time_horizon": "1-5 days",
                "recommended_action": "increase_risk",
                "reasoning_summary": (
                    "Inflation is cooling faster than consensus, which raises the probability of earlier and deeper "
                    "policy easing. Lower real rates support long-duration growth equities and crypto, while the "
                    "defensive bid fades."
                ),
                "impacts": [("QQQ", "positive", 86), ("SPY", "positive", 72), ("IWM", "positive", 78),
                            ("TLT", "positive", 80), ("BTC", "positive", 66), ("GLD", "positive", 48),
                            ("XLE", "negative", 40)],
                "actions": [("QQQ", "INCREASE", 8), ("IWM", "INCREASE", 6), ("BTC", "INCREASE", 4),
                            ("TLT", "INCREASE", 3), ("XLE", "REDUCE", 4)],
            },
            price_shocks={"QQQ": 0.021, "SPY": 0.014, "IWM": 0.019, "TLT": 0.016, "BTC": 0.024, "GLD": 0.006,
                          "XLE": -0.011},
        ),
        EventTemplate(
            key="earnings_beat_nvda",
            label="Earnings beat - NVIDIA",
            group="Earnings",
            category="earnings",
            importance="high",
            source="NVIDIA IR / Bloomberg",
            title="NVIDIA beats earnings expectations and raises data-centre guidance",
            summary=(
                "NVIDIA reported Q3 revenue of $49.3bn versus $44.1bn expected and EPS of $0.94 versus $0.81. "
                "Data-centre revenue grew 62% q/q and management raised Q4 guidance above consensus, citing "
                "Blackwell demand exceeding supply. Semiconductor peers rallied in after-hours trade."
            ),
            affected_assets=("NVDA", "QQQ", "SOXX", "SPY", "MSFT"),
            description="Single-name beat with sector read-through to semiconductors.",
            expected_analysis={
                "event_type": "earnings",
                "sentiment": "bullish",
                "market_regime": "risk_on",
                "confidence": 0.91,
                "time_horizon": "1-5 days",
                "recommended_action": "increase_risk",
                "reasoning_summary": (
                    "A large beat-and-raise from the AI capex bellwether. Earnings revisions propagate through the "
                    "semiconductor complex and lift the index because of NVDA's weight in QQQ."
                ),
                "impacts": [("NVDA", "positive", 93), ("SOXX", "positive", 78), ("QQQ", "positive", 64),
                            ("SPY", "positive", 41), ("MSFT", "positive", 46)],
                "actions": [("NVDA", "INCREASE", 9), ("SOXX", "INCREASE", 5), ("QQQ", "INCREASE", 3)],
            },
            price_shocks={"NVDA": 0.062, "SOXX": 0.028, "QQQ": 0.013, "SPY": 0.007, "MSFT": 0.011},
        ),
        EventTemplate(
            key="earnings_miss_aapl",
            label="Earnings miss - Apple",
            group="Earnings",
            category="earnings",
            importance="high",
            source="Apple IR / CNBC",
            title="Apple misses revenue expectations on weak Greater China iPhone sales",
            summary=(
                "Apple reported revenue of $89.1bn versus $93.4bn expected. iPhone revenue fell 8% y/y with Greater "
                "China down 16%. Management flagged component cost inflation and guided gross margin below consensus "
                "for the next quarter."
            ),
            affected_assets=("AAPL", "QQQ", "SPY", "SOXX"),
            description="Mega-cap miss; index drag plus supply-chain read-through.",
            expected_analysis={
                "event_type": "earnings",
                "sentiment": "bearish",
                "market_regime": "risk_off",
                "confidence": 0.83,
                "time_horizon": "1-5 days",
                "recommended_action": "reduce_risk",
                "reasoning_summary": (
                    "A mega-cap revenue miss with weak guidance is an index-level drag given AAPL's weight, and the "
                    "China weakness spreads to the wider hardware supply chain."
                ),
                "impacts": [("AAPL", "negative", 90), ("QQQ", "negative", 62), ("SPY", "negative", 44),
                            ("SOXX", "negative", 47)],
                "actions": [("AAPL", "REDUCE", 12), ("QQQ", "REDUCE", 5), ("SOXX", "REDUCE", 4)],
            },
            price_shocks={"AAPL": -0.058, "QQQ": -0.012, "SPY": -0.008, "SOXX": -0.014},
        ),
        EventTemplate(
            key="oil_supply_shock",
            label="Oil supply shock",
            group="Commodities",
            category="commodity",
            importance="critical",
            source="OPEC+ / Reuters",
            title="OPEC+ announces surprise 1.5mb/d cut as Brent breaks above $95",
            summary=(
                "OPEC+ announced an unexpected 1.5 million barrel-per-day supply cut effective immediately. Brent "
                "spiked 7.4% to $95.80. Breakeven inflation expectations moved higher and the market pulled forward "
                "its expectation for the next policy hike."
            ),
            affected_assets=("USO", "XLE", "SPY", "QQQ", "TLT", "GLD"),
            description="Stagflationary shock: energy up, rate-sensitive assets down.",
            expected_analysis={
                "event_type": "commodity",
                "sentiment": "mixed",
                "market_regime": "risk_off",
                "confidence": 0.79,
                "time_horizon": "1-4 weeks",
                "recommended_action": "rotate",
                "reasoning_summary": (
                    "A supply-driven energy shock is stagflationary: it benefits producers and energy equities while "
                    "raising breakevens, which hurts duration and consumer-discretionary growth names."
                ),
                "impacts": [("USO", "positive", 91), ("XLE", "positive", 84), ("SPY", "negative", 58),
                            ("QQQ", "negative", 66), ("TLT", "negative", 62), ("GLD", "positive", 57)],
                "actions": [("XLE", "INCREASE", 7), ("USO", "INCREASE", 5), ("QQQ", "REDUCE", 6),
                            ("GLD", "INCREASE", 3), ("TLT", "REDUCE", 4)],
            },
            price_shocks={"USO": 0.071, "XLE": 0.044, "SPY": -0.011, "QQQ": -0.016, "TLT": -0.013, "GLD": 0.012},
        ),
        EventTemplate(
            key="geopolitical_escalation",
            label="Geopolitical escalation",
            group="Geopolitics",
            category="geopolitical",
            importance="critical",
            source="AP / Reuters",
            title="Geopolitical escalation in the Strait of Hormuz; VIX futures spike 32%",
            summary=(
                "Naval incidents in the Strait of Hormuz disrupted roughly 20% of global seaborne crude transit. "
                "Equity index volatility surged, safe-haven flows accelerated into gold and the yen, and airlines "
                "and shipping names sold off on rerouting costs."
            ),
            affected_assets=("GLD", "TLT", "SPY", "QQQ", "USO", "BTC"),
            description="Classic flight-to-quality: hedges up, beta down.",
            expected_analysis={
                "event_type": "geopolitical",
                "sentiment": "bearish",
                "market_regime": "risk_off",
                "confidence": 0.81,
                "time_horizon": "1-5 days",
                "recommended_action": "hedge",
                "reasoning_summary": (
                    "A tail-risk geopolitical shock with an immediate transmission channel through energy supply and "
                    "shipping. Correlations converge in risk assets while gold and duration absorb the safe-haven bid."
                ),
                "impacts": [("GLD", "positive", 88), ("TLT", "positive", 71), ("USO", "positive", 83),
                            ("SPY", "negative", 74), ("QQQ", "negative", 79), ("BTC", "negative", 52)],
                "actions": [("QQQ", "REDUCE", 12), ("SPY", "REDUCE", 8), ("GLD", "INCREASE", 8),
                            ("TLT", "INCREASE", 5), ("BTC", "REDUCE", 6)],
            },
            price_shocks={"GLD": 0.026, "TLT": 0.014, "USO": 0.058, "SPY": -0.023, "QQQ": -0.029, "BTC": -0.031,
                          "IWM": -0.027},
        ),
        EventTemplate(
            key="crypto_regulation_positive",
            label="Crypto regulation - positive",
            group="Crypto",
            category="crypto",
            importance="high",
            source="SEC / CoinDesk",
            title="US regulators approve spot Ethereum ETFs and publish a digital-asset market structure framework",
            summary=(
                "The SEC approved 19b-4 filings for spot Ethereum ETFs and, jointly with the CFTC, published a "
                "market-structure framework clarifying custody and token classification. Institutional flows into "
                "regulated crypto products are expected to accelerate."
            ),
            affected_assets=("BTC", "ETH", "QQQ"),
            description="Regulatory clarity re-rates digital assets higher.",
            expected_analysis={
                "event_type": "crypto_regulation",
                "sentiment": "bullish",
                "market_regime": "risk_on",
                "confidence": 0.88,
                "time_horizon": "1-4 weeks",
                "recommended_action": "increase_risk",
                "reasoning_summary": (
                    "Regulatory clarity removes a persistent valuation overhang and opens regulated distribution "
                    "channels. ETH has the larger marginal re-rating because the ETF approval was the binding "
                    "constraint; BTC benefits from the broader institutional bid."
                ),
                "impacts": [("ETH", "positive", 92), ("BTC", "positive", 81), ("QQQ", "positive", 34)],
                "actions": [("ETH", "INCREASE", 7), ("BTC", "INCREASE", 5)],
            },
            price_shocks={"ETH": 0.082, "BTC": 0.047, "QQQ": 0.004},
        ),
        EventTemplate(
            key="crypto_regulation_negative",
            label="Crypto regulation - negative",
            group="Crypto",
            category="crypto",
            importance="high",
            source="FinCEN / The Block",
            title="Treasury proposes strict stablecoin reserve rules; major exchange halts US withdrawals",
            summary=(
                "Treasury proposed mandatory 1:1 short-dated Treasury backing for all stablecoins issued to US "
                "persons with a 90-day compliance window. A top-five exchange simultaneously halted USD withdrawals "
                "citing a liquidity review, and BTC funding rates turned deeply negative."
            ),
            affected_assets=("BTC", "ETH", "QQQ"),
            description="Regulatory shock plus counterparty stress in digital assets.",
            expected_analysis={
                "event_type": "crypto_regulation",
                "sentiment": "bearish",
                "market_regime": "risk_off",
                "confidence": 0.86,
                "time_horizon": "1-5 days",
                "recommended_action": "reduce_risk",
                "reasoning_summary": (
                    "Combined regulatory tightening and an exchange liquidity event is the most damaging pairing for "
                    "digital assets because it attacks both the funding rail and counterparty trust at once."
                ),
                "impacts": [("BTC", "negative", 89), ("ETH", "negative", 91), ("QQQ", "negative", 28),
                            ("GLD", "positive", 41)],
                "actions": [("BTC", "REDUCE", 14), ("ETH", "REDUCE", 16), ("GLD", "INCREASE", 4)],
            },
            price_shocks={"BTC": -0.064, "ETH": -0.081, "QQQ": -0.006, "GLD": 0.008},
        ),
        EventTemplate(
            key="gdp_strong",
            label="GDP release - upside surprise",
            group="Macro data",
            category="gdp",
            importance="high",
            source="Bureau of Economic Analysis",
            title="US Q3 GDP revised up to 3.4% annualised, consumer spending leads",
            summary=(
                "Real GDP grew at a 3.4% annualised rate versus 2.6% expected. Final sales to domestic purchasers "
                "accelerated and the savings rate fell, suggesting the expansion is being funded out of cash buffers "
                "rather than income growth."
            ),
            affected_assets=("SPY", "QQQ", "IWM", "TLT", "JPM"),
            description="Growth upside, but with a rates cost.",
            expected_analysis={
                "event_type": "growth",
                "sentiment": "mixed",
                "market_regime": "risk_on",
                "confidence": 0.72,
                "time_horizon": "1-4 weeks",
                "recommended_action": "rotate",
                "reasoning_summary": (
                    "Stronger growth supports cyclicals and financials, but a hot print delays easing and hurts "
                    "duration. The right expression is a rotation rather than a blanket risk-on add."
                ),
                "impacts": [("SPY", "positive", 61), ("IWM", "positive", 68), ("JPM", "positive", 72),
                            ("QQQ", "positive", 44), ("TLT", "negative", 66)],
                "actions": [("JPM", "INCREASE", 6), ("IWM", "INCREASE", 5), ("TLT", "REDUCE", 7),
                            ("QQQ", "INCREASE", 2)],
            },
            price_shocks={"SPY": 0.008, "IWM": 0.014, "JPM": 0.017, "QQQ": 0.005, "TLT": -0.012},
        ),
        EventTemplate(
            key="jobs_report_hot",
            label="Employment report - too hot",
            group="Macro data",
            category="employment",
            importance="high",
            source="Bureau of Labor Statistics",
            title="Nonfarm payrolls beat by 190k as wage growth re-accelerates to 4.6%",
            summary=(
                "Payrolls rose 372k versus 182k expected and the unemployment rate held at 3.8%. Average hourly "
                "earnings rose 0.6% m/m, the fastest in eleven months, reviving concerns about a wage-price spiral."
            ),
            affected_assets=("SPY", "QQQ", "TLT", "IWM", "GLD"),
            description="Good news is bad news: rates higher, multiples lower.",
            expected_analysis={
                "event_type": "employment",
                "sentiment": "bearish",
                "market_regime": "risk_off",
                "confidence": 0.76,
                "time_horizon": "1-5 days",
                "recommended_action": "reduce_risk",
                "reasoning_summary": (
                    "A hot labour market with re-accelerating wages removes the disinflation argument for easing. "
                    "Higher-for-longer policy compresses equity multiples and hurts long duration."
                ),
                "impacts": [("TLT", "negative", 79), ("QQQ", "negative", 70), ("SPY", "negative", 58),
                            ("IWM", "negative", 64), ("GLD", "negative", 46), ("JPM", "positive", 49)],
                "actions": [("TLT", "REDUCE", 9), ("QQQ", "REDUCE", 7), ("IWM", "REDUCE", 5), ("JPM", "INCREASE", 4)],
            },
            price_shocks={"TLT": -0.018, "QQQ": -0.015, "SPY": -0.010, "IWM": -0.016, "GLD": -0.007, "JPM": 0.009},
        ),
        EventTemplate(
            key="illiquid_meme_pump",
            label="Illiquid micro-cap pump (risk engine demo)",
            group="Stress test",
            category="other",
            importance="medium",
            source="Social sentiment aggregator",
            title="Viral social campaign targets illiquid micro-cap ILLIQ; retail flow surges",
            summary=(
                "A coordinated social-media campaign is driving volume in ILLIQ, a micro-cap with under $1m of "
                "average daily dollar volume and realised volatility above 130% annualised. Sentiment tools score "
                "the move as extremely bullish but the name is effectively untradeable at size."
            ),
            affected_assets=("ILLIQ",),
            description="Deliberately trips liquidity, volatility and position limits so the risk engine rejects.",
            expected_analysis={
                "event_type": "other",
                "sentiment": "bullish",
                "market_regime": "risk_on",
                "confidence": 0.94,
                "time_horizon": "intraday",
                "recommended_action": "increase_risk",
                "reasoning_summary": (
                    "Extremely bullish retail momentum signal in a micro-cap. Note the venue is thin: average daily "
                    "dollar volume is far below institutional participation thresholds."
                ),
                "impacts": [("ILLIQ", "positive", 97)],
                "actions": [("ILLIQ", "BUY", 30)],
            },
            price_shocks={"ILLIQ": 0.045},
        ),
        EventTemplate(
            key="low_confidence_rumour",
            label="Unconfirmed rumour (confidence gate demo)",
            group="Stress test",
            category="other",
            importance="low",
            source="Anonymous social post",
            title="Unverified rumour circulates about a surprise acquisition",
            summary=(
                "An unverified post claims a large-cap technology company is in advanced talks to be acquired. No "
                "filing, no confirmation from either company, and no corroborating outlet has picked the story up."
            ),
            affected_assets=("MSFT",),
            description="Low-confidence input that the risk engine must filter out.",
            expected_analysis={
                "event_type": "other",
                "sentiment": "bullish",
                "market_regime": "neutral",
                "confidence": 0.31,
                "time_horizon": "intraday",
                "recommended_action": "hold",
                "reasoning_summary": (
                    "Single unverified source with no corroboration and no regulatory filing. Confidence is low and "
                    "the base rate for rumour-driven M&A completing near-term is poor."
                ),
                "impacts": [("MSFT", "positive", 38)],
                "actions": [("MSFT", "INCREASE", 4)],
            },
            price_shocks={},
        ),
    ]
}


TEMPLATE_ORDER: List[str] = [
    "fed_hawkish_hold",
    "cpi_surprise_low",
    "earnings_beat_nvda",
    "earnings_miss_aapl",
    "oil_supply_shock",
    "geopolitical_escalation",
    "crypto_regulation_positive",
    "crypto_regulation_negative",
    "gdp_strong",
    "jobs_report_hot",
    "illiquid_meme_pump",
    "low_confidence_rumour",
]


# Historical events seeded at boot so the live feed is never empty.
SEEDED_EVENTS: List[Dict[str, Any]] = [
    {
        "minutes_ago": 4,
        "title": "Fed's Logan: 'We are not done with inflation' as markets pare cut bets",
        "source": "Reuters",
        "category": "central_bank",
        "importance": "high",
        "summary": (
            "Dallas Fed president Logan pushed back on easing expectations, saying services inflation remains "
            "sticky. Two-year yields firmed 4bp on the comments."
        ),
        "affected_assets": ["TLT", "QQQ", "SPY"],
    },
    {
        "minutes_ago": 22,
        "title": "NVIDIA Blackwell shipments begin; supply constrained through Q1",
        "source": "Bloomberg",
        "category": "earnings",
        "importance": "high",
        "summary": (
            "Supply-chain checks show Blackwell accelerators shipping to three hyperscalers, with lead times still "
            "above 30 weeks. Semis outperform the tape."
        ),
        "affected_assets": ["NVDA", "SOXX", "QQQ"],
    },
    {
        "minutes_ago": 47,
        "title": "US 10-year Treasury yield climbs to 4.42% on supply indigestion",
        "source": "FT",
        "category": "macro",
        "importance": "medium",
        "summary": (
            "The 10-year auction tailed by 2.1bp with weak indirect bidding. Duration underperforms and the equity "
            "risk premium is being repriced."
        ),
        "affected_assets": ["TLT", "SPY", "QQQ"],
    },
    {
        "minutes_ago": 76,
        "title": "Spot Bitcoin ETFs log ninth straight day of net inflows",
        "source": "CoinDesk",
        "category": "crypto",
        "importance": "medium",
        "summary": (
            "Aggregate net inflows reached $1.9bn over nine sessions, the longest positive streak since launch. "
            "Exchange balances continue to fall."
        ),
        "affected_assets": ["BTC", "ETH"],
    },
    {
        "minutes_ago": 118,
        "title": "OPEC+ delegates signal no change to voluntary cuts before the March meeting",
        "source": "Reuters",
        "category": "commodity",
        "importance": "medium",
        "summary": (
            "Three delegates said the group sees the market balanced and will not adjust quotas early. Brent holds "
            "a $78-$84 range."
        ),
        "affected_assets": ["USO", "XLE"],
    },
    {
        "minutes_ago": 165,
        "title": "Gold holds near record as central-bank buying offsets stronger dollar",
        "source": "WSJ",
        "category": "commodity",
        "importance": "medium",
        "summary": (
            "Official-sector purchases ran at 64 tonnes last month. Gold remains the preferred hedge in a "
            "higher-for-longer rate regime."
        ),
        "affected_assets": ["GLD"],
    },
    {
        "minutes_ago": 232,
        "title": "Apple cuts Vision Pro output plan by a third on soft demand",
        "source": "Nikkei",
        "category": "earnings",
        "importance": "low",
        "summary": (
            "Assembly partners were told to reduce the build plan. The read-through to the wider AAPL supply chain "
            "is modest but negative."
        ),
        "affected_assets": ["AAPL", "QQQ"],
    },
    {
        "minutes_ago": 310,
        "title": "ECB's Lane: disinflation on track, June decision 'genuinely open'",
        "source": "Bloomberg",
        "category": "central_bank",
        "importance": "medium",
        "summary": (
            "The ECB chief economist kept a first-cut optionality alive. EUR cross-asset implications are second "
            "order for a US-focused book."
        ),
        "affected_assets": ["EEM", "SPY"],
    },
    {
        "minutes_ago": 420,
        "title": "Red Sea rerouting pushes container spot rates up 18% week on week",
        "source": "FT",
        "category": "geopolitical",
        "importance": "medium",
        "summary": (
            "Shipping disruption is adding two to three weeks to Asia-Europe lanes and is starting to show up in "
            "goods inflation inputs."
        ),
        "affected_assets": ["SPY", "XLE", "GLD"],
    },
    {
        "minutes_ago": 540,
        "title": "US initial jobless claims fall to 208k, lowest since September",
        "source": "DOL",
        "category": "employment",
        "importance": "medium",
        "summary": (
            "Labour market resilience continues to complicate the easing narrative. Small caps lag on the print."
        ),
        "affected_assets": ["IWM", "SPY", "TLT"],
    },
    {
        "minutes_ago": 690,
        "title": "Microsoft raises Copilot seat prices for enterprise tier",
        "source": "The Information",
        "category": "earnings",
        "importance": "low",
        "summary": (
            "Pricing power in AI software is showing up earlier than consensus expected. Margin accretive at the "
            "intelligent-cloud segment."
        ),
        "affected_assets": ["MSFT", "QQQ"],
    },
    {
        "minutes_ago": 850,
        "title": "JPMorgan lifts NII guidance on deposit repricing",
        "source": "CNBC",
        "category": "earnings",
        "importance": "medium",
        "summary": (
            "Large-cap banks are benefiting from slower deposit beta. Financials are the strongest sector on the "
            "session."
        ),
        "affected_assets": ["JPM", "SPY"],
    },
]
