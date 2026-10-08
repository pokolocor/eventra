"""Request IDs, structured logging and safe error reporting.

Nothing here leaks internals: `safe_detail()` is the only place an exception is
converted into a client-visible string, and in production it returns a static
message plus the request ID so support can be correlated with server logs.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.config import Settings

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_BYTES = 16

# Exception types whose message is safe to show a caller: they are written by
# Eventra itself for humans, and contain no internals.
_SAFE_MESSAGE_TYPES = ("ValidationError", "HttpError", "SecurityError", "KeyError")

GENERIC_ERROR = "Internal server error."

# Anything that could carry a credential out of the LLM client.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer|api[-_]?key|authorization|token)\b\s*[:=]?\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)(https?://[^\s/?]+)[^\s]*\?[^\s]*"),
)


def sanitize_llm_error(exc: BaseException) -> str:
    """A client-safe description of an LLM failure.

    Keeps the failure class and a short reason (so the dashboard can explain a
    degraded run) while stripping credentials and query strings.
    """

    text = str(exc).strip() or type(exc).__name__
    for pattern in _SECRET_PATTERNS[:-1]:
        text = pattern.sub("[redacted]", text)
    text = _SECRET_PATTERNS[-1].sub(lambda m: m.group(1), text)
    return f"{type(exc).__name__}: {text}"[:300]


def new_request_id() -> str:
    return uuid.uuid4().hex[:REQUEST_ID_BYTES * 2]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line - what Render's log stream expects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(settings: Settings) -> logging.Logger:
    """Idempotently configure the root `eventra` logger."""

    logger = logging.getLogger("eventra")
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(handler)

    formatter: logging.Formatter
    if settings.log_format == "text":
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s %(message)s", datefmt="%H:%M:%S"
        )
    else:
        formatter = JsonLogFormatter()

    for handler in logger.handlers:
        handler.setFormatter(formatter)
        handler.setLevel(level)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"eventra.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    request_id: str = "",
    **fields: Any,
) -> None:
    logger.log(level, message, extra={"request_id": request_id, "extra_fields": fields})


def _is_safe_type(exc: BaseException) -> bool:
    return any(part in _SAFE_MESSAGE_TYPES for part in _type_chain(exc))


def _type_chain(exc: BaseException) -> list:
    chain = []
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return chain


def safe_detail(exc: BaseException, settings: Settings, request_id: str = "") -> str:
    """Client-safe description of a failure.

    Development keeps the useful `Type: message` string; production returns a
    static message (plus the request ID) so tracebacks and internals never
    reach the browser.
    """

    if settings.is_production:
        suffix = f" (request {request_id})" if request_id else ""
        return f"{GENERIC_ERROR}{suffix}"
    message = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {message}"[:500]


def startup_warnings(settings: Settings) -> list:
    """Configuration problems worth shouting about at boot."""

    warnings = []
    if not settings.database_configured:
        warnings.append("DATABASE_URL not set - using ephemeral store")
    if settings.is_production and not settings.admin_auth_configured:
        warnings.append(
            "ADMIN_TOKEN not set in production - the control plane is disabled (fail closed)"
        )
    if settings.is_production and not settings.qwen_available and not settings.demo_mode:
        warnings.append(
            "QWEN_API_KEY not set and demo mode disabled - agent runs cannot be analysed"
        )
    if not settings.is_production and not settings.admin_auth_configured:
        warnings.append("ADMIN_TOKEN not set - control endpoints are unauthenticated (development only)")
    return warnings


def log_startup(settings: Settings, store_kind: str) -> None:
    logger = get_logger("boot")
    logger.info(
        "eventra starting",
        extra={
            "extra_fields": {
                "environment": settings.environment,
                "mode": "PAPER / DEMO" if settings.demo_mode else "PAPER",
                "paper_trading_only": settings.paper_trading_only,
                "llm_provider": "qwen" if settings.qwen_available else "demo-mock",
                "llm_configured": settings.qwen_available,
                "store": store_kind,
                "persistent": settings.database_configured,
                "admin_auth_required": settings.admin_auth_required,
                "cors_origins": settings.cors_origins,
            }
        },
    )
    for warning in startup_warnings(settings):
        logger.warning(warning)
