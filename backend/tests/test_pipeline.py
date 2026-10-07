"""End-to-end agent pipeline: Event -> Qwen -> Signal -> Risk -> Trade -> Portfolio."""

from __future__ import annotations

import json
import time

from backend.api import handlers
from backend.models.domain import PipelineStage, RiskStatus
from backend.services.qwen_service import QwenService
from backend.tests.support import make_event, make_registry, run_template

EXPECTED_ORDER = [
    PipelineStage.EVENT_DETECTED,
    PipelineStage.QWEN_ANALYSIS,
    PipelineStage.MARKET_IMPACT,
    PipelineStage.SIGNAL_GENERATED,
    PipelineStage.RISK_CHECK,
    PipelineStage.EXECUTION,
    PipelineStage.PORTFOLIO_UPDATED,
]


def test_full_chain_runs_in_order(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "fed_hawkish_hold")
    assert run.status == "completed"
    stages = [entry.stage for entry in run.timeline]
    assert stages == EXPECTED_ORDER
    assert all(entry.detail for entry in run.timeline)


def test_analysis_signal_and_risk_are_attached(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "earnings_beat_nvda")
    assert run.analysis is not None and run.signal is not None and run.risk is not None
    assert run.signal.event_id == run.event.id
    assert run.analysis.sentiment.value == "bullish"
    assert run.risk.status in (RiskStatus.APPROVED, RiskStatus.REDUCED)
    assert run.portfolio_after is not None


def test_explanation_is_human_readable(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "fed_hawkish_hold")
    text = run.explanation
    assert "confidence" in text.lower()
    assert "PAPER" in text
    assert len(text) > 120


def test_rejected_run_stops_before_execution(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "illiquid_meme_pump")
    stages = [entry.stage for entry in run.timeline]
    assert PipelineStage.PORTFOLIO_UPDATED in stages
    execution_entry = next(e for e in run.timeline if e.stage == PipelineStage.EXECUTION)
    assert execution_entry.status == "error"
    assert run.trades == []


def test_decision_is_persisted_and_retrievable(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "cpi_surprise_low")
    fetched = registry.orchestrator.get_run(run.id)
    assert fetched is not None and fetched.id == run.id
    assert len(registry.orchestrator.list_runs(limit=10)) >= 1


def test_decision_serialises_to_json(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "geopolitical_escalation")
    payload = handlers.decision_to_dict(run)
    encoded = json.dumps(payload, default=str)
    assert json.loads(encoded)["summary"]["risk_status"] in {"APPROVED", "REDUCED", "REJECTED"}
    assert payload["risk"]["checks"]["liquidity"] in {"PASS", "WARN", "FAIL"}


def test_async_run_completes(tmp_path):
    registry = make_registry(tmp_path)
    decision_id = registry.orchestrator.start_run(template_key="crypto_regulation_positive")
    deadline = time.time() + 10
    run = None
    while time.time() < deadline:
        run = registry.orchestrator.get_run(decision_id)
        if run is not None and run.status != "running":
            break
        time.sleep(0.05)
    assert run is not None and run.status == "completed"
    assert len(run.timeline) == len(EXPECTED_ORDER)


def test_real_qwen_path_is_used_when_key_present(tmp_path):
    registry = make_registry(tmp_path)
    registry.settings.qwen_api_key = "test-key"
    payload = {
        "event_type": "monetary_policy",
        "sentiment": "bearish",
        "market_regime": "risk_off",
        "confidence": 0.87,
        "affected_assets": [{"symbol": "QQQ", "direction": "negative", "impact_score": 82}],
        "time_horizon": "1-5 days",
        "recommended_action": "reduce_risk",
        "portfolio_actions": [{"symbol": "QQQ", "action": "REDUCE", "percentage": 6}],
        "reasoning_summary": "Hawkish guidance compresses long-duration multiples.",
    }
    registry.qwen = QwenService(
        config=registry.settings,
        transport=lambda request: {"choices": [{"message": {"content": json.dumps(payload)}}]},
    )
    service, mode = registry.llm()
    assert mode == "qwen"

    run = run_template(registry, "fed_hawkish_hold")
    assert run.llm_provider == "qwen"
    assert run.analysis.confidence == 0.87
    assert run.analysis.provider == "qwen"


def test_qwen_failure_is_surfaced_not_silently_mocked(tmp_path):
    """A configured-but-broken Qwen must fail loudly, never swap in mock data."""

    registry = make_registry(tmp_path)
    registry.settings.qwen_api_key = "test-key"

    def broken_transport(request):
        return {"choices": [{"message": {"content": "I cannot help with that."}}]}

    registry.qwen = QwenService(config=registry.settings, transport=broken_transport)
    run = run_template(registry, "fed_hawkish_hold")
    assert run.status == "failed"
    assert run.analysis is None
    assert run.trades == []
    assert run.error and "validation" in run.error.lower()
    failed_stage = next(e for e in run.timeline if e.status == "error")
    assert failed_stage.stage.value == "qwen_analysis"


def test_demo_mode_only_engages_without_an_api_key(tmp_path):
    registry = make_registry(tmp_path)
    assert registry.settings.qwen_api_key == ""
    service, mode = registry.llm()
    assert mode == "demo"
    run = run_template(registry, "fed_hawkish_hold")
    assert run.llm_provider == "demo-mock"
    assert "DEMO MODE" in (run.analysis.raw_output or "")


def test_portfolio_stays_solvent_across_many_events(tmp_path):
    registry = make_registry(tmp_path)
    keys = [
        "fed_hawkish_hold", "cpi_surprise_low", "earnings_beat_nvda",
        "geopolitical_escalation", "oil_supply_shock", "crypto_regulation_negative",
    ]
    for index, key in enumerate(keys):
        registry.repository.set_kill_switch(False)
        state = registry.repository.load_system()
        state.signals = []  # clear duplicate cooldown between stress iterations
        registry.repository.save_system(state)
        run_template(registry, key)
        snapshot = registry.portfolio.snapshot(persist=False)
        assert snapshot.cash >= -0.01, f"cash went negative after {key}"
        assert snapshot.portfolio_value > 0
        assert snapshot.exposure <= registry.settings.risk_limits.max_gross_exposure_pct + 0.5


def test_arbitrary_event_payload_runs_the_pipeline(tmp_path):
    registry = make_registry(tmp_path)
    run = registry.orchestrator.run_sync(
        event_payload={
            "title": "Unexpected resignation of the US Treasury Secretary",
            "source": "Reuters",
            "category": "policy",
            "importance": "high",
            "summary": "Markets react to a sudden leadership vacuum in US economic policy.",
            "affected_assets": ["SPY", "TLT", "GLD"],
        }
    )
    assert run.status == "completed"
    assert run.analysis is not None
    assert run.event.title.startswith("Unexpected resignation")


def test_system_status_reports_agent_activity(tmp_path):
    registry = make_registry(tmp_path)
    run_template(registry, "jobs_report_hot")
    status = handlers.system_status(registry)
    assert status["counts"]["events"] > 0
    assert status["agent"]["decisions_total"] >= 1
    assert status["llm"]["provider"] == "demo-mock"
    assert status["mode"] == "PAPER / DEMO"


def test_make_event_helper_is_valid(tmp_path):
    event = make_event(title="Helper event", assets=["spy", "QQQ"])
    assert event.affected_assets == ["SPY", "QQQ"]


def test_rejected_explanation_reads_cleanly(tmp_path):
    registry = make_registry(tmp_path)
    run = run_template(registry, "illiquid_meme_pump")
    assert run.risk is not None and run.risk.status == RiskStatus.REJECTED
    text = run.explanation
    assert "REJECTED" in text
    assert "because Blocked by" not in text
    assert ".." not in text
    assert "No paper trade was executed" in text


def test_duplicate_signal_explanation_names_the_blocker(tmp_path):
    registry = make_registry(tmp_path)
    run_template(registry, "cpi_surprise_low")
    repeat = run_template(registry, "cpi_surprise_low")
    assert repeat.risk is not None and repeat.risk.status == RiskStatus.REJECTED
    assert "Blocked by duplicate_signal" in repeat.explanation
    assert ".." not in repeat.explanation