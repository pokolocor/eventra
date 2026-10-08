"""Transport-agnostic control-plane security.

Both the FastAPI app (`backend/main.py`) and the zero-dependency dev server
(`backend/dev_server.py`) enforce the *same* rules by calling into this module,
so "authorised" has exactly one definition and it is unit-testable without a
web framework installed.

Guarantees
----------
* Admin secrets are compared in constant time and never logged or echoed back.
* Production fails closed: with no `ADMIN_TOKEN`, the control plane is disabled
  rather than left public.
* Rate limiting is a sliding window per client IP and returns `Retry-After`.
* Error details are static strings - no exception text reaches the client.
"""

from __future__ import annotations

import hmac
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Mapping, Optional

from backend.config import Settings
from backend.observability import REQUEST_ID_HEADER

ADMIN_TOKEN_HEADER = "X-Admin-Token"
BEARER_PREFIX = "bearer "
FORWARDED_FOR_HEADER = "X-Forwarded-For"
REAL_IP_HEADER = "X-Real-IP"

UNKNOWN_IP = "unknown"


# --- errors --------------------------------------------------------------
class SecurityError(Exception):
    """Base class for every control-plane rejection.

    Carries an HTTP status plus optional response headers. `detail` is always a
    static, client-safe string.
    """

    status = 400

    def __init__(self, detail: str, *, headers: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers: Dict[str, str] = dict(headers or {})


class UnauthorizedError(SecurityError):
    status = 401


class ForbiddenError(SecurityError):
    status = 403


class RateLimitedError(SecurityError):
    status = 429

    def __init__(
        self,
        detail: str,
        *,
        retry_after: int = 1,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        merged = {"Retry-After": str(max(1, int(retry_after)))}
        merged.update(dict(headers or {}))
        super().__init__(detail, headers=merged)
        self.retry_after = max(1, int(retry_after))


class ControlPlaneDisabledError(SecurityError):
    status = 503


# --- headers -------------------------------------------------------------
def get_header(headers: Any, name: str) -> Optional[str]:
    """Case-insensitive header lookup.

    Works with FastAPI/Starlette `Headers`, `email.message.Message` (stdlib
    `http.server`), and plain dicts.
    """

    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        try:
            value = getter(name)
        except Exception:  # pragma: no cover - defensive
            value = None
        if value is None and hasattr(headers, "keys"):
            try:
                for key in headers.keys():
                    if str(key).lower() == name.lower():
                        value = getter(key)
                        break
            except Exception:  # pragma: no cover - defensive
                value = None
        if value is not None:
            return str(value)
    if hasattr(headers, "keys"):
        try:
            for key in headers.keys():
                if str(key).lower() == name.lower():
                    return str(headers[key])
        except Exception:  # pragma: no cover - defensive
            return None
    return None


def extract_admin_token(headers: Any) -> Optional[str]:
    """Pull the admin secret from `X-Admin-Token` or `Authorization: Bearer`."""

    direct = get_header(headers, ADMIN_TOKEN_HEADER)
    if direct and direct.strip():
        return direct.strip()

    authorization = get_header(headers, "Authorization")
    if authorization and authorization.strip():
        value = authorization.strip()
        if value.lower().startswith(BEARER_PREFIX):
            token = value[len(BEARER_PREFIX):].strip()
            return token or None
    return None


def client_ip(headers: Any, remote_addr: Optional[str] = None) -> str:
    """Best-effort client IP, honouring the proxy headers Render sets."""

    forwarded = get_header(headers, FORWARDED_FOR_HEADER)
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = get_header(headers, REAL_IP_HEADER)
    if real_ip and real_ip.strip():
        return real_ip.strip()
    if remote_addr and remote_addr.strip():
        return remote_addr.strip()
    return UNKNOWN_IP


# --- principals ----------------------------------------------------------
@dataclass(frozen=True)
class Principal:
    """Who is calling, for audit purposes."""

    actor: str
    authenticated: bool
    ip: str = UNKNOWN_IP
    request_id: str = ""

    @property
    def audit_actor(self) -> str:
        return self.actor


def anonymous(ip: str = UNKNOWN_IP, request_id: str = "") -> Principal:
    return Principal(actor="anonymous", authenticated=False, ip=ip, request_id=request_id)


def require_admin(settings: Settings, headers: Any, remote_addr: Optional[str] = None) -> Principal:
    """Authorise a control-plane call.

    * Token configured  -> must be presented and match (constant-time compare).
    * No token, prod    -> 503, the control plane is disabled (fail closed).
    * No token, dev     -> allowed, so the local demo stays usable.
    """

    ip = client_ip(headers, remote_addr)
    request_id = get_header(headers, REQUEST_ID_HEADER) or ""
    expected = settings.admin_token.strip()

    if expected:
        presented = extract_admin_token(headers)
        challenge = {"WWW-Authenticate": "Bearer"}
        if not presented:
            raise UnauthorizedError(
                "Authentication required. Send 'Authorization: Bearer <ADMIN_TOKEN>' "
                f"or the '{ADMIN_TOKEN_HEADER}' header.",
                headers=challenge,
            )
        if not hmac.compare_digest(presented, expected):
            raise UnauthorizedError("Invalid admin token.", headers=challenge)
        return Principal(actor="admin", authenticated=True, ip=ip, request_id=request_id)

    if settings.is_production:
        raise ControlPlaneDisabledError(
            "Control plane disabled: ADMIN_TOKEN is not configured on this deployment."
        )

    return Principal(actor="dev-local", authenticated=False, ip=ip, request_id=request_id)


def require_reset_allowed(settings: Settings) -> None:
    """`/system/reset` is a demo affordance; production must opt in explicitly."""

    if not settings.reset_allowed:
        raise ForbiddenError(
            "Demo reset is disabled in production. Set ALLOW_DEMO_RESET=true to enable it."
        )


# --- rate limiting -------------------------------------------------------
class RateLimiter:
    """Thread-safe sliding-window limiter keyed by an arbitrary string.

    `limit <= 0` disables the limiter. Raises `RateLimitedError` with a
    computed `Retry-After` once the window is full.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        clock: Any = time.monotonic,
        max_keys: int = 4096,
    ) -> None:
        self.limit = int(limit)
        self.window = float(window_seconds)
        self._clock = clock
        self._max_keys = max(64, int(max_keys))
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def _prune(self, bucket: Deque[float], now: float) -> None:
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def check(self, key: str) -> int:
        """Record one hit for `key`; return the remaining allowance."""

        if not self.enabled:
            return -1
        now = self._clock()
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= self._max_keys:
                    self._evict_stale(now)
                bucket = self._hits.setdefault(key, deque())
            self._prune(bucket, now)

            if len(bucket) >= self.limit:
                retry_after = max(1, int(math.ceil(bucket[0] + self.window - now)))
                raise RateLimitedError(
                    f"Rate limit exceeded: {self.limit} request(s) per "
                    f"{int(self.window)}s for this endpoint.",
                    retry_after=retry_after,
                    headers={
                        "X-RateLimit-Limit": str(self.limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            bucket.append(now)
            return self.limit - len(bucket)

    def _evict_stale(self, now: float) -> None:
        cutoff = now - self.window
        for key in list(self._hits):
            bucket = self._hits[key]
            self._prune(bucket, now)
            if not bucket or (bucket[-1] <= cutoff):
                self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class ConcurrencyGuard:
    """Global single-flight guard for the agent pipeline.

    The dashboard already shows "Agent is already working"; this makes that a
    server-side guarantee and returns 429 + `Retry-After` instead of letting
    runs pile up on one process.
    """

    def __init__(self, max_concurrent: int = 1, retry_after: int = 5) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.retry_after = max(1, int(retry_after))
        self._active = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self.max_concurrent:
                return False
            self._active += 1
            return True

    def acquire(self) -> None:
        if not self.try_acquire():
            raise RateLimitedError(
                "Agent is already working an event. Try again shortly.",
                retry_after=self.retry_after,
                headers={"X-RateLimit-Limit": str(self.max_concurrent)},
            )

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    def reset(self) -> None:
        with self._lock:
            self._active = 0


@dataclass
class Guard:
    """Holds the limiters for one process. Attached to the service registry."""

    settings: Settings
    agent: RateLimiter = field(init=False)
    control: RateLimiter = field(init=False)
    concurrency: ConcurrencyGuard = field(init=False)

    def __post_init__(self) -> None:
        self.agent = RateLimiter(self.settings.agent_rate_limit_per_minute, 60.0)
        self.control = RateLimiter(self.settings.control_rate_limit_per_minute, 60.0)
        self.concurrency = ConcurrencyGuard(max_concurrent=1, retry_after=5)

    def check_agent(self, ip: str) -> None:
        self.agent.check(f"agent:{ip}")

    def check_control(self, ip: str, action: str) -> None:
        self.control.check(f"control:{action}:{ip}")

    def reset(self) -> None:
        self.agent.reset()
        self.control.reset()
        self.concurrency.reset()
