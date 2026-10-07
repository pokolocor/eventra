"""Qwen LLM service - the interpretation layer of Eventra.

Responsibilities
----------------
* Send a normalised market event to Qwen (OpenAI-compatible chat completions).
* Demand a strict JSON schema back.
* Validate that JSON into `QwenAnalysis` (Pydantic). Reject anything malformed.
* Retry once with a repair instruction before giving up.
* Never touch the portfolio. The output is only ever a *proposal*.

The API key is read exclusively from the environment (`QWEN_API_KEY`). If it is
missing, this service raises `QwenUnavailableError` and the orchestrator decides
whether to fall back to Demo Mode. No mock responses live in this module.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from backend.config import Settings, settings as default_settings
from backend.models.domain import Event, QwenAnalysis

SYSTEM_PROMPT = """You are Eventra's market interpretation engine.
You convert a single financial event into a strict, machine-readable trading thesis.

Rules:
- You analyse. You never place orders and you never assume an order will be executed.
- Every numeric field must respect its documented range.
- impact_score is 0-100 (100 = maximum expected price impact).
- confidence is a probability between 0 and 1.
- Only include portfolio_actions you would genuinely defend. Use percentages of the
  CURRENT portfolio weight for that symbol (0-100).
- Respond with a single JSON object and nothing else. No prose, no markdown fences.

Required JSON schema:
{
  "event_type": "macro | monetary_policy | inflation | employment | growth | earnings | geopolitical | crypto_regulation | commodity | other",
  "sentiment": "bullish | bearish | neutral | mixed",
  "market_regime": "risk_on | risk_off | neutral",
  "confidence": 0.0,
  "affected_assets": [{"symbol": "TICKER", "direction": "positive | negative | neutral", "impact_score": 0}],
  "time_horizon": "intraday | 1-5 days | 1-4 weeks | 1-6 months",
  "recommended_action": "increase_risk | reduce_risk | hold | hedge | rotate",
  "portfolio_actions": [{"symbol": "TICKER", "action": "BUY | SELL | INCREASE | REDUCE | HOLD | HEDGE", "percentage": 0}],
  "reasoning_summary": "One tight paragraph a portfolio manager can read in ten seconds."
}"""

REPAIR_PROMPT = """Your previous reply could not be parsed into the required schema.
Validation errors:
{errors}

Reply again with ONLY the corrected JSON object. No markdown, no commentary."""


class QwenServiceError(Exception):
    """Base class for every Qwen service failure."""


class QwenUnavailableError(QwenServiceError):
    """Raised when no API key is configured."""


class QwenAPIError(QwenServiceError):
    """Raised on transport / HTTP / provider errors."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class QwenValidationError(QwenServiceError):
    """Raised when Qwen returns something that fails schema validation."""

    def __init__(self, message: str, raw: str = "", attempts: int = 1) -> None:
        super().__init__(message)
        self.raw = raw
        self.attempts = attempts


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Dict[str, Any]:
    """Best-effort extraction of the first JSON object from a model reply."""

    if not text or not text.strip():
        raise QwenValidationError("Qwen returned an empty response")

    candidates: List[str] = []
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error: Optional[Exception] = None
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = QwenValidationError("Qwen returned JSON that is not an object")
    raise QwenValidationError(
        f"Could not extract a JSON object from Qwen response: {last_error}", raw=text
    )


class QwenService:
    """Thin, dependency-free client for the Qwen chat completions API."""

    def __init__(self, config: Optional[Settings] = None, transport: Optional[Any] = None) -> None:
        self.config = config or default_settings
        # `transport` is injectable for tests: callable(payload) -> dict
        self._transport = transport

    # --- public API -----------------------------------------------------
    @property
    def available(self) -> bool:
        return self.config.qwen_available

    @property
    def endpoint(self) -> str:
        return f"{self.config.qwen_base_url}/chat/completions"

    def build_messages(self, event: Event) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self.build_user_prompt(event)},
        ]

    def build_user_prompt(self, event: Event) -> str:
        payload = {
            "timestamp": event.timestamp.isoformat(),
            "title": event.title,
            "source": event.source,
            "category": event.category.value,
            "importance": event.importance.value,
            "summary": event.summary,
            "affected_assets_hint": event.affected_assets,
            "raw": event.raw,
        }
        return (
            "Analyse this market event and return the JSON object only.\n\n"
            f"EVENT:\n{json.dumps(payload, indent=2, default=str)}"
        )

    def analyze_event(self, event: Event) -> QwenAnalysis:
        """Run Qwen against an event and return a validated analysis."""

        if not self.available:
            raise QwenUnavailableError(
                "QWEN_API_KEY is not configured. Start the API with a key, or run in Demo Mode."
            )

        messages = self.build_messages(event)
        started = time.perf_counter()
        last_raw = ""
        attempts = 0
        last_error: Optional[Exception] = None

        for attempt in range(self.config.qwen_max_retries + 1):
            attempts = attempt + 1
            try:
                completion = self._chat(messages)
            except QwenAPIError as exc:
                # Transport failures are not worth a repair prompt.
                raise QwenAPIError(str(exc), getattr(exc, "status_code", None)) from exc

            last_raw = completion
            try:
                data = extract_json(completion)
                analysis = QwenAnalysis.model_validate(data)
            except (QwenValidationError, ValidationError) as exc:
                last_error = exc
                messages = messages + [
                    {"role": "assistant", "content": completion},
                    {"role": "user", "content": REPAIR_PROMPT.format(errors=str(exc)[:1200])},
                ]
                continue

            analysis.provider = "qwen"
            analysis.model = self.config.qwen_model
            analysis.latency_ms = int((time.perf_counter() - started) * 1000)
            analysis.attempts = attempts
            analysis.raw_output = last_raw[:8000]
            return analysis

        raise QwenValidationError(
            f"Qwen response failed schema validation after {attempts} attempt(s): {last_error}",
            raw=last_raw,
            attempts=attempts,
        )

    # --- transport ------------------------------------------------------
    def _chat(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.config.qwen_model,
            "messages": messages,
            "temperature": self.config.qwen_temperature,
            "response_format": {"type": "json_object"},
        }
        if self._transport is not None:
            response = self._transport(payload)
        else:
            response = self._http_post(payload)

        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise QwenAPIError(f"Unexpected Qwen response envelope: {exc}") from exc
        if isinstance(content, list):  # some deployments return content parts
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise QwenAPIError("Qwen returned no message content")
        return content

    def _http_post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.qwen_api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.qwen_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # pragma: no cover - best effort diagnostics
                pass
            raise QwenAPIError(f"Qwen API HTTP {exc.code}: {detail or exc.reason}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise QwenAPIError(f"Qwen API unreachable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise QwenAPIError("Qwen API timed out") from exc
        except json.JSONDecodeError as exc:
            raise QwenAPIError(f"Qwen API returned invalid JSON: {exc}") from exc
