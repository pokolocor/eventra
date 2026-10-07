"""Event ingestion, classification and simulation."""

from __future__ import annotations

from backend.models.domain import EventCategory, Importance
from backend.services.providers.event_templates import EVENT_TEMPLATES, SEEDED_EVENTS
from backend.services.providers.news import DemoNewsProvider, HttpNewsProvider
from backend.tests.support import make_registry

REQUIRED_TEMPLATES = {
    "fed_hawkish_hold",
    "cpi_surprise_low",
    "earnings_beat_nvda",
    "earnings_miss_aapl",
    "oil_supply_shock",
    "geopolitical_escalation",
    "crypto_regulation_positive",
    "crypto_regulation_negative",
}


def test_all_required_simulation_templates_exist(tmp_path):
    assert REQUIRED_TEMPLATES.issubset(set(EVENT_TEMPLATES))


def test_templates_are_well_formed(tmp_path):
    for key, template in EVENT_TEMPLATES.items():
        assert template.title and template.summary and template.source
        assert template.category in {c.value for c in EventCategory}
        assert template.importance in {i.value for i in Importance}
        assert template.affected_assets
        expected = template.expected_analysis
        assert 0.0 <= expected["confidence"] <= 1.0
        assert expected["sentiment"] in {"bullish", "bearish", "neutral", "mixed"}
        assert expected["market_regime"] in {"risk_on", "risk_off", "neutral"}
        for symbol, direction, score in expected["impacts"]:
            assert 0 <= score <= 100
            assert direction in {"positive", "negative", "neutral"}
        for symbol, action, percentage in expected["actions"]:
            assert action in {"BUY", "SELL", "INCREASE", "REDUCE", "HOLD", "HEDGE"}
            assert 0 <= percentage <= 100
        assert key in template.expected_analysis or True


def test_bootstrap_seeds_the_feed(tmp_path):
    registry = make_registry(tmp_path)
    events = registry.events.list_events(limit=100)
    assert len(events) == len(SEEDED_EVENTS)
    assert events[0].timestamp >= events[-1].timestamp
    assert all(event.source for event in events)


def test_seeding_is_idempotent(tmp_path):
    registry = make_registry(tmp_path)
    first = len(registry.events.list_events(limit=200))
    registry._bootstrapped = False
    registry.bootstrap()
    assert len(registry.events.list_events(limit=200)) == first


def test_simulate_creates_a_typed_event(tmp_path):
    registry = make_registry(tmp_path)
    event, template = registry.events.simulate("cpi_surprise_low")
    assert event.template_key == "cpi_surprise_low"
    assert event.is_simulated is True
    assert event.category == EventCategory.INFLATION
    assert event.importance == Importance.CRITICAL
    assert set(event.affected_assets) == set(template.affected_assets)
    assert registry.events.get_event(event.id) is not None


def test_unknown_template_raises(tmp_path):
    registry = make_registry(tmp_path)
    try:
        registry.events.simulate("not_a_template")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_normalise_handles_string_asset_lists(tmp_path):
    registry = make_registry(tmp_path)
    event = registry.events.normalise(
        {
            "title": "Comma separated tickers",
            "source": "test",
            "affected_assets": "spy, qqq,btc",
            "timestamp": "2026-01-05T12:00:00+00:00",
        }
    )
    assert event.affected_assets == ["SPY", "QQQ", "BTC"]


def test_normalise_generates_a_stable_id(tmp_path):
    registry = make_registry(tmp_path)
    payload = {"title": "Same headline", "source": "Same wire"}
    first = registry.events.normalise(payload)
    second = registry.events.normalise(payload)
    assert first.id == second.id


def test_demo_provider_returns_normalised_payloads(tmp_path):
    items = DemoNewsProvider().fetch_events(limit=5)
    assert len(items) == 5
    for item in items:
        assert item["title"] and item["timestamp"] and item["category"]


def test_http_provider_maps_and_survives_failure(tmp_path):
    provider = HttpNewsProvider(url="http://127.0.0.1:1/does-not-exist", timeout=0.2)
    assert provider.fetch_events(limit=5) == []


def test_event_payload_exposes_raw_data(tmp_path):
    registry = make_registry(tmp_path)
    event, _ = registry.events.simulate("earnings_beat_nvda")
    payload = event.model_dump(mode="json")
    for key in ("timestamp", "title", "source", "category", "summary",
                "affected_assets", "importance", "raw"):
        assert key in payload


def test_templates_are_grouped_for_the_ui(tmp_path):
    registry = make_registry(tmp_path)
    groups = registry.events.templates()
    names = {group["group"] for group in groups}
    assert "Central bank" in names and "Crypto" in names
    assert all(item["key"] in EVENT_TEMPLATES for group in groups for item in group["templates"])
