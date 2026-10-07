"""Eventra configuration.

All secrets come from environment variables (or a local `.env` file). Nothing is
ever hard-coded, and the frontend never sees any of these values - the browser
only talks to the Eventra API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

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
            duplicate_signal_cooldown_minutes=_get_int("EVENTRA_DUPLICATE_COOLDOWN_MIN", 30),
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

    # --- Runtime mode ---------------------------------------------------
    demo_mode: bool = True
    paper_trading_only: bool = True

    # --- Persistence ----------------------------------------------------
    database_url: str = "sqlite:///./data/eventra.db"
    data_dir: Path = BACKEND_DIR / "data"

    # --- Portfolio ------------------------------------------------------
    starting_balance: float = 1_000_000.0
    starting_cash: float = 350_000.0

    # --- API ------------------------------------------------------------
    cors_origins: List[str] = field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    risk_limits: RiskLimits = field(default_factory=RiskLimits)

    @property
    def qwen_available(self) -> bool:
        return bool(self.qwen_api_key.strip())

    @property
    def llm_mode(self) -> str:
        """`qwen` when a real key is configured, otherwise `demo`."""

        return "qwen" if self.qwen_available else "demo"

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
            "database": {
                "url": _redact(self.database_url),
                "backend": _db_backend(self.database_url),
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
    return url.split(":", 1)[0] or "unknown"


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or DEFAULT_ENV_FILE)
    limits = RiskLimits.from_env()
    cors_raw = os.environ.get("EVENTRA_CORS_ORIGINS", "")
    cors = [o.strip() for o in cors_raw.split(",") if o.strip()]
    return Settings(
        qwen_api_key=os.environ.get("QWEN_API_KEY", "").strip(),
        qwen_base_url=os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/"),
        qwen_model=os.environ.get("QWEN_MODEL", "qwen-plus").strip() or "qwen-plus",
        qwen_timeout_seconds=_get_float("QWEN_TIMEOUT_SECONDS", 30.0),
        qwen_max_retries=_get_int("QWEN_MAX_RETRIES", 2),
        qwen_temperature=_get_float("QWEN_TEMPERATURE", 0.2),
        demo_mode=_get_bool("EVENTRA_DEMO_MODE", True),
        paper_trading_only=_get_bool("EVENTRA_PAPER_TRADING_ONLY", True),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./data/eventra.db").strip(),
        data_dir=Path(os.environ.get("EVENTRA_DATA_DIR", str(BACKEND_DIR / "data"))),
        starting_balance=_get_float("EVENTRA_STARTING_BALANCE", 1_000_000.0),
        starting_cash=_get_float("EVENTRA_STARTING_CASH", 350_000.0),
        cors_origins=cors or Settings().cors_origins,
        risk_limits=limits,
    )


settings = load_settings()
