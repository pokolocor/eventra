"""SQLAlchemy engine/session wiring.

Imported lazily so the project still runs when SQLAlchemy is not installed
(Demo Mode uses `JsonFileRepository`).
"""

from __future__ import annotations

from typing import Any, Optional

from backend.config import BACKEND_DIR, Settings


def resolve_database_url(settings: Settings) -> str:
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        relative = url.replace("sqlite:///./", "", 1)
        target = (BACKEND_DIR / relative).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{target.as_posix()}"
    return url


def create_engine_for(settings: Settings) -> Any:
    from sqlalchemy import create_engine

    url = resolve_database_url(settings)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, future=True, connect_args=connect_args)


def create_session_factory(settings: Settings) -> Any:
    from sqlalchemy.orm import sessionmaker

    engine = create_engine_for(settings)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def sqlalchemy_available() -> bool:
    try:
        import sqlalchemy  # noqa: F401
    except Exception:
        return False
    return True


def database_is_configured(settings: Settings) -> bool:
    """True when a real SQL backend is both requested and importable."""

    return sqlalchemy_available() and bool(settings.database_url.strip())


def try_init_schema(settings: Settings) -> Optional[Any]:
    from backend.database.orm import Base

    engine = create_engine_for(settings)
    Base.metadata.create_all(engine)
    return engine
