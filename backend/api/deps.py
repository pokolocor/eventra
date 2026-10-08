"""Shared FastAPI dependencies.

Authentication lives here so the routers stay declarative. The actual rules are
in `backend/security.py`, which the stdlib dev server uses too - one policy, two
transports.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from backend.security import (
    REQUEST_ID_HEADER,
    Principal,
    SecurityError,
    anonymous,
    client_ip,
    get_header,
    require_admin,
)
from backend.services.registry import ServiceRegistry, get_registry


def registry() -> ServiceRegistry:
    return get_registry()


def _remote_addr(request: Request) -> str:
    return request.client.host if request.client else ""


def _request_id(request: Request) -> str:
    state_value = getattr(request.state, "request_id", "")
    return state_value or get_header(request.headers, REQUEST_ID_HEADER) or ""


def request_principal(request: Request) -> Principal:
    """Caller identity (IP + request id) for unauthenticated endpoints."""

    return anonymous(client_ip(request.headers, _remote_addr(request)), _request_id(request))


def admin_principal(request: Request) -> Principal:
    """Enforce the control-plane token; 401/403/503 on failure."""

    service = get_registry()
    try:
        return require_admin(service.settings, request.headers, _remote_addr(request))
    except SecurityError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.detail, headers=exc.headers or None
        ) from exc


AdminPrincipal = Depends(admin_principal)
CallerPrincipal = Depends(request_principal)
