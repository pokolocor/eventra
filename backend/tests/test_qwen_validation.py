"""Qwen response parsing, validation and failure handling."""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.qwen_service import (
    QwenAPIError,
    QwenService,
    QwenUnavailableError,
    QwenValidationError,
    extract_json,
)
from backend.tests.support import make_event, make_settings

VALID_PAYLOAD = {
    "event_type": "monetary_policy",
    "sentiment": "bearish",
    "market_regime": "risk_off",
    "confidence": 0.87,
    "affected_assets": [
        {"symbol": "qqq", "direction": "negative", "impact_score": 82},
        {"symbol": "TLT", "direction": "positive", "impact_score": 68},
    ],
    "time_horizon": "1-5 days",
    "recommended_action": "reduce_risk",
    "portfolio_actions": [
        {"symbol": "QQQ", "action": "reduce", "percentage": 10},
        {"symbol": "TLT", "action": "INCREASE", "percentage": 5},
        {"symbol": "GLD", "action": "HOLD", "percentage": 0},
    ],
    "reasoning_summary": "Hawkish hold raises the discount rate for long-duration growth assets.",
}


def _service(tmp: Path, transport=None, key: str = "test-key") -> QwenService:
    settings = make_settings(tmp, qwen_api_key=key)
    return QwenService(config=settings, transport=transport)


def test_extract_json_accepts_bare_object(tmp_path):
    assert extract_json(json.dumps(VALID_PAYLOAD))["sentiment"] == "bearish"


def test_extract_json_strips_markdown_fence(tmp_path):
    text = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
    assert extract_json(text)["confidence"] == 0.87


def test_extract_json_ignores_surrounding_prose(tmp_path):
    text = "Sure! Here is the analysis:\n" + json.dumps(VALID_PAYLOAD) + "\nHope that helps."
    assert extract_json(text)["market_regime"] == "risk_off"


def test_extract_json_rejects_garbage(tmp_path):
    try:
        extract_json("the market is complicated and I refuse to answer in JSON")
    except QwenValidationError:
        return
    raise AssertionError("expected QwenValidationError")


def test_extract_json_rejects_empty(tmp_path):
    try:
        extract_json("   ")
    except QwenValidationError:
        return
    raise AssertionError("expected QwenValidationError")


def test_valid_response_is_accepted_and_normalised(tmp_path):
    service = _service(tmp_path, transport=lambda payload: {
        "choices": [{"message": {"content": json.dumps(VALID_PAYLOAD)}}]
    })
    analysis = service.analyze_event(make_event())

    assert analysis.sentiment.value == "bearish"
    assert analysis.confidence == 0.87
    assert analysis.affected_assets[0].symbol == "QQQ"
    # HOLD actions with zero size are stripped as non-actionable.
    assert [a.symbol for a in analysis.portfolio_actions] == ["QQQ", "TLT"]
    assert analysis.portfolio_actions[0].action.value == "REDUCE"
    assert analysis.provider == "qwen"
    assert analysis.attempts == 1


def test_confidence_given_as_percentage_is_rescaled(tmp_path):
    payload = dict(VALID_PAYLOAD, confidence=87)
    service = _service(tmp_path, transport=lambda p: {"choices": [{"message": {"content": json.dumps(payload)}}]})
    assert service.analyze_event(make_event()).confidence == 0.87


def test_impact_score_given_as_fraction_is_rescaled(tmp_path):
    payload = json.loads(json.dumps(VALID_PAYLOAD))
    payload["affected_assets"][0]["impact_score"] = 0.82
    service = _service(tmp_path, transport=lambda p: {"choices": [{"message": {"content": json.dumps(payload)}}]})
    assert service.analyze_event(make_event()).affected_assets[0].impact_score == 82


def test_invalid_enum_is_rejected(tmp_path):
    payload = dict(VALID_PAYLOAD, sentiment="very_bearish")
    service = _service(tmp_path, transport=lambda p: {"choices": [{"message": {"content": json.dumps(payload)}}]})
    try:
        service.analyze_event(make_event())
    except QwenValidationError as exc:
        assert exc.attempts >= 1
        return
    raise AssertionError("expected QwenValidationError")


def test_malformed_then_repaired_succeeds_on_second_attempt(tmp_path):
    calls = {"n": 0}

    def transport(payload):
        calls["n"] += 1
        content = "not json at all" if calls["n"] == 1 else json.dumps(VALID_PAYLOAD)
        return {"choices": [{"message": {"content": content}}]}

    analysis = _service(tmp_path, transport=transport).analyze_event(make_event())
    assert calls["n"] == 2
    assert analysis.attempts == 2
    assert analysis.confidence == 0.87


def test_persistently_malformed_response_raises(tmp_path):
    service = _service(tmp_path, transport=lambda p: {"choices": [{"message": {"content": "sorry"}}]})
    try:
        service.analyze_event(make_event())
    except QwenValidationError as exc:
        assert exc.attempts == 3  # initial attempt + 2 retries
        return
    raise AssertionError("expected QwenValidationError")


def test_missing_api_key_raises_unavailable(tmp_path):
    service = _service(tmp_path, key="")
    assert service.available is False
    try:
        service.analyze_event(make_event())
    except QwenUnavailableError:
        return
    raise AssertionError("expected QwenUnavailableError")


def test_api_error_is_wrapped(tmp_path):
    def transport(payload):
        raise QwenAPIError("Qwen API HTTP 429: rate limited", 429)

    try:
        _service(tmp_path, transport=transport).analyze_event(make_event())
    except QwenAPIError as exc:
        assert exc.status_code == 429
        return
    raise AssertionError("expected QwenAPIError")


def test_empty_message_content_raises(tmp_path):
    service = _service(tmp_path, transport=lambda p: {"choices": [{"message": {"content": ""}}]})
    try:
        service.analyze_event(make_event())
    except QwenAPIError:
        return
    raise AssertionError("expected QwenAPIError")


def test_unexpected_envelope_raises(tmp_path):
    service = _service(tmp_path, transport=lambda p: {"oops": True})
    try:
        service.analyze_event(make_event())
    except QwenAPIError:
        return
    raise AssertionError("expected QwenAPIError")


def test_prompt_contains_event_and_schema(tmp_path):
    service = _service(tmp_path)
    messages = service.build_messages(make_event(title="Fed holds rates steady"))
    assert messages[0]["role"] == "system"
    assert "portfolio_actions" in messages[0]["content"]
    assert "Fed holds rates steady" in messages[1]["content"]
