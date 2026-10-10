"""Eventra configuration.

All secrets come from environment variables (or a local `.env` file). Nothing is
ever hard-coded, and the frontend never sees any of these values - the browser
only talks to the Eventra API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    """Minimal `.env` loader so the project runs without python-dotenv."""

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(float(raw)) if raw not in (None, "") else default
    except ValueError:
        return default


def _first_env(*names: str) -> Optional[str]:
    """Return the first non-empty value among `names`, else None.

    Used for env aliases so both the documented name (`CORS_ORIGINS`) and the
    legacy Eventra-prefixed name (`EVENTRA_CORS_ORIGINS`) keep working.
    """

    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return None


def _first_bool(names: Tuple[str, ...], default: bool) -> bool:
    """Boolean from the first alias that is actually present in the env."""

    for name in names:
        if os.environ.get(name) is not None:
            return _get_bool(name, default)
    return default


def _first_int(names: Tuple[str, ...], default: int) -> int:
    for name in names:
        if os.environ.get(name) is not None:
            return _get_int(name, default)
    return default


def _first_float(names: Tuple[str, ...], default: float) -> float:
    for name in names:
        if os.environ.get(name) is not None:
            return _get_float(name, default)
    return default


# Origin of the deployed dashboard. Kept in the CORS default so a fresh Render
# deploy is reachable even before `CORS_ORIGINS` is set; `CORS_ORIGINS` always
# wins when present. This is a *frontend* origin, not an API endpoint.
DEFAULT_PROD_FRONTEND_ORIGIN = "https://eventra-frontend-sy4w.onrender.com"

DEFAULT_CORS_ORIGINS: Tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    DEFAULT_PROD_FRONTEND_ORIGIN,
)

PRODUCTION_WORDS = {"prod", "production"}


def _resolve_environment() -> str:
    """`production` when explicitly asked for, or when running on Render."""

    explicit = _first_env("EVENTRA_ENV", "ENVIRONMENT", "APP_ENV")
    if explicit:
        return (
            "production" if explicit.lower() in PRODUCTION_WORDS else explicit.lower()
        )
    if _get_bool("RENDER", False) or _first_env("RENDER_SERVICE_ID"):
        return "production"
    return "development"


@dataclass
class RiskLimits:
    """Deterministic guard-rails. The LLM can never modify these."""

    max_position_weight_pct: float = 25.0
    max_gross_exposure_pct: float = 90.0
    max_trade_notional: float = 150_000.0
    max_single_trade_pct: float = 12.0
    max_daily_loss_pct: float = 4.0
    min_confidence: float = 0.60
    min_adv_usd: float = 250_000_000.0
    max_trade_adv_pct: float = 2.0
    max_annualized_vol: float = 0.90
    duplicate_signal_cooldown_minutes: int = 30
    max_actions_per_decision: int = 6

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_position_weight_pct": self.max_position_weight_pct,
            "max_gross_exposure_pct": self.max_gross_exposure_pct,
            "max_trade_notional": self.max_trade_notional,
            "max_single_trade_pct": self.max_single_trade_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "min_confidence": self.min_confidence,
            "min_adv_usd": self.min_adv_usd,
            "max_trade_adv_pct": self.max_trade_adv_pct,
            "max_annualized_vol": self.max_annualized_vol,
            "duplicate_signal_cooldown_minutes": self.duplicate_signal_cooldown_minutes,
            "max_actions_per_decision": self.max_actions_per_decision,
        }

    @classmethod
    def from_env(cls) -> "RiskLimits":
        return cls(
            max_position_weight_pct=_get_float("EVENTRA_MAX_POSITION_WEIGHT_PCT", 25.0),
            max_gross_exposure_pct=_get_float("EVENTRA_MAX_GROSS_EXPOSURE_PCT", 90.0),
            max_trade_notional=_get_float("EVENTRA_MAX_TRADE_NOTIONAL", 150_000.0),
            max_single_trade_pct=_get_float("EVENTRA_MAX_SINGLE_TRADE_PCT", 12.0),
            max_daily_loss_pct=_get_float("EVENTRA_MAX_DAILY_LOSS_PCT", 4.0),
            min_confidence=_get_float("EVENTRA_MIN_CONFIDENCE", 0.60),
            min_adv_usd=_get_float("EVENTRA_MIN_ADV_USD", 250_000_000.0),
            max_trade_adv_pct=_get_float("EVENTRA_MAX_TRADE_ADV_PCT", 2.0),
            max_annualized_vol=_get_float("EVENTRA_MAX_ANNUALIZED_VOL", 0.90),
            duplicate_signal_cooldown_minutes=_get_int(
                "EVENTRA_DUPLICATE_COOLDOWN_MIN", 30
            ),
            max_actions_per_decision=_get_int("EVENTRA_MAX_ACTIONS_PER_DECISION", 6),
        )


@dataclass
class Settings:
    app_name: str = "Eventra"
    tagline: str = "From Events to Execution"
    version: str = "1.0.0"

    # --- LLM (Qwen) -----------------------------------------------------
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_timeout_seconds: float = 30.0
    qwen_max_retries: int = 2
    qwen_temperature: float = 0.2

    # --- Bitget Demo Trading --------------------------------------------
    bitget_api_key: str = ""
    bitget_api_secret: str = ""
    bitget_passphrase: str = ""

    # --- Runtime mode ---------------------------------------------------
    demo_mode: bool = True
    paper_trading_only: bool = True

    # --- Persistence ----------------------------------------------------
    # Empty means "not configured": Eventra then uses the ephemeral store and
    # logs a loud startup warning instead of silently losing state on reboot.
    database_url: str = ""
    data_dir: Path = BACKEND_DIR / "data"

    # --- Portfolio ------------------------------------------------------
    starting_balance: float = 1_000_000.0
    starting_cash: float = 350_000.0

    # --- API ------------------------------------------------------------
    cors_origins: List[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))

    # --- Control plane --------------------------------------------------
    # Secret required by kill-switch / reset / event ingestion. Never sent to
    # the browser: the Next.js server proxies it (see frontend/src/app/api).
    admin_token: str = ""
    environment: str = "development"
    allow_demo_reset: bool = False

    # --- Abuse control --------------------------------------------------
    agent_rate_limit_per_minute: int = 10
    control_rate_limit_per_minute: int = 30

    # --- Observability --------------------------------------------------
    log_level: str = "INFO"
    log_format: str = "json"

    # --- Market simulation ---------------------------------------------
    market_tick: int = 0

    risk_limits: RiskLimits = field(default_factory=RiskLimits)

    @property
    def qwen_available(self) -> bool:
        return bool(self.qwen_api_key.strip())

    @property
    def bitget_available(self) -> bool:
        """True when Bitget API keys are configured."""
        return bool(self.bitget_api_key.strip() and self.bitget_api_secret.strip())

    @property
    def llm_mode(self) -> str:
        """`qwen` when a real key is configured, otherwise `demo`."""

        return "qwen" if self.qwen_available else "demo"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in PRODUCTION_WORDS

    @property
    def admin_auth_configured(self) -> bool:
        """True when an ADMIN_TOKEN secret is present."""

        return bool(self.admin_token.strip())

    @property
    def admin_auth_required(self) -> bool:
        """True when control-plane calls must carry a token.

        Production fails closed: with no token configured the control plane is
        disabled entirely rather than left public.
        """

        return self.admin_auth_configured or self.is_production

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url.strip())

    @property
    def reset_allowed(self) -> bool:
        """`/system/reset` is a demo affordance; production must opt in."""

        return True if not self.is_production else bool(self.allow_demo_reset)

    @property
    def store_label(self) -> str:
        """Human label for the STORE badge, derived from configuration."""

        return (
            _db_backend(self.database_url) if self.database_configured else "ephemeral"
        )

    def public_status(self) -> Dict[str, Any]:
        return {
            "app": self.app_name,
            "tagline": self.tagline,
            "version": self.version,
            "mode": "PAPER / DEMO" if self.demo_mode else "PAPER",
            "paper_trading_only": self.paper_trading_only,
            "llm": {
                "provider": "qwen" if self.qwen_available else "demo-mock",
                "model": self.qwen_model,
                "configured": self.qwen_available,
                "base_url": self.qwen_base_url,
            },
            "bitget": {
                "configured": self.bitget_available,
                "mode": "demo",
            },
            "database": {
                "url": _redact(self.database_url),
                "backend": self.store_label,
                "persistent": self.database_configured,
            },
            "environment": self.environment,
            "control_plane": {
                "admin_auth_required": self.admin_auth_required,
                "admin_token_configured": self.admin_auth_configured,
                "reset_allowed": self.reset_allowed,
            },
            "rate_limits": {
                "agent_per_minute": self.agent_rate_limit_per_minute,
                "control_per_minute": self.control_rate_limit_per_minute,
            },
            "risk_limits": self.risk_limits.as_dict(),
            "cors_origins": self.cors_origins,
        }


def _redact(url: str) -> str:
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _creds, _, host = rest.partition("@")
    return f"{scheme}://***:***@{host}"


def _db_backend(url: str) -> str:
    if url.startswith("postgres"):
        return "postgresql"
    if url.startswith("sqlite"):
        return "sqlite"
    return url.split(":", 1)[0] or "ephemeral"


def _resolve_cors_origins() -> List[str]:
    """Comma-separated allow-list. `CORS_ORIGINS` wins over the legacy alias."""

    raw = _first_env("CORS_ORIGINS", "EVENTRA_CORS_ORIGINS") or ""
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def _resolve_demo_mode() -> bool:
    """`EVENTRA_DEMO_MODE` wins; otherwise `MODE=demo|paper` decides."""

    if os.environ.get("EVENTRA_DEMO_MODE") is not None:
        return _get_bool("EVENTRA_DEMO_MODE", True)
    mode = _first_env("MODE", "EVENTRA_MODE")
    if mode:
        return mode.lower() in {"demo", "demo-mock", "mock"}
    return True


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or DEFAULT_ENV_FILE)
    return Settings(
        qwen_api_key=os.environ.get("QWEN_API_KEY", "").strip(),
        qwen_base_url=(
            _first_env("QWEN_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/"),
        qwen_model=os.environ.get("QWEN_MODEL", "qwen-plus").strip() or "qwen-plus",
        qwen_timeout_seconds=_first_float(
            ("QWEN_TIMEOUT_SECONDS", "LLM_TIMEOUT_SECONDS"), 15.0
        ),
        qwen_max_retries=_first_int(("QWEN_MAX_RETRIES", "LLM_MAX_RETRIES"), 2),
        qwen_temperature=_get_float("QWEN_TEMPERATURE", 0.2),
        bitget_api_key=os.environ.get("BITGET_API_KEY", "").strip(),
        bitget_api_secret=os.environ.get("BITGET_API_SECRET", "").strip(),
        bitget_passphrase=os.environ.get("BITGET_PASSPHRASE", "").strip(),
        demo_mode=_resolve_demo_mode(),
        # Hard guarantee. Paper trading only, always.
        paper_trading_only=_get_bool("EVENTRA_PAPER_TRADING_ONLY", True),
        database_url=_first_env("DATABASE_URL", "EVENTRA_DATABASE_URL") or "",
        data_dir=Path(_first_env("EVENTRA_DATA_DIR") or str(BACKEND_DIR / "data")),
        starting_balance=_get_float("EVENTRA_STARTING_BALANCE", 1_000_000.0),
        starting_cash=_get_float("EVENTRA_STARTING_CASH", 350_000.0),
        cors_origins=_resolve_cors_origins(),
        admin_token=_first_env("ADMIN_TOKEN", "EVENTRA_ADMIN_TOKEN") or "",
        environment=_resolve_environment(),
        allow_demo_reset=_first_bool(
            ("ALLOW_DEMO_RESET", "EVENTRA_ALLOW_DEMO_RESET"), False
        ),
        agent_rate_limit_per_minute=_first_int(
            ("EVENTRA_AGENT_RATE_LIMIT_PER_MIN", "AGENT_RATE_LIMIT_PER_MIN"), 10
        ),
        control_rate_limit_per_minute=_first_int(
            ("EVENTRA_CONTROL_RATE_LIMIT_PER_MIN", "CONTROL_RATE_LIMIT_PER_MIN"), 30
        ),
        log_level=(_first_env("EVENTRA_LOG_LEVEL", "LOG_LEVEL") or "INFO").upper(),
        log_format=(_first_env("EVENTRA_LOG_FORMAT", "LOG_FORMAT") or "json").lower(),
        market_tick=_first_int(("MARKET_TICK", "EVENTRA_MARKET_TICK"), 0),
        risk_limits=RiskLimits.from_env(),
    )


settings = load_settings()
