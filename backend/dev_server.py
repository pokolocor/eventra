"""Zero-dependency Eventra dev server.

Serves the exact same JSON API as the FastAPI app (both delegate to
`backend/api/handlers.py`) plus the bundled demo terminal UI, using only the
Python standard library. This is what lets Eventra run - and be judged - on a
machine with no `pip install` step.

Production path: `uvicorn backend.main:app`.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from backend.api import handlers
from backend.config import BACKEND_DIR
from backend.services.registry import get_registry

STATIC_DIR = BACKEND_DIR / "static"

Route = Tuple[str, re.Pattern, Callable[..., Any]]
ROUTES: List[Route] = []


def route(method: str, pattern: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    compiled = re.compile(f"^{pattern}$")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        ROUTES.append((method.upper(), compiled, func))
        return func

    return decorator


class HttpError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _int_arg(params: Dict[str, List[str]], key: str, default: int) -> int:
    try:
        return int(params.get(key, [default])[0])
    except (TypeError, ValueError):
        return default


# --- system -------------------------------------------------------------
@route("GET", r"/api/health")
def _health(**_: Any) -> Dict[str, Any]:
    service = get_registry()
    return {
        "status": "ok",
        "app": service.settings.app_name,
        "tagline": service.settings.tagline,
        "mode": "PAPER / DEMO" if service.settings.demo_mode else "PAPER",
        "llm_provider": service.llm()[1],
        "kill_switch": service.repository.get_kill_switch(),
    }


@route("GET", r"/api/system/status")
def _status(**_: Any) -> Dict[str, Any]:
    return handlers.system_status(get_registry())


@route("GET", r"/api/system/audit")
def _audit(params: Dict[str, List[str]], **_: Any) -> List[Dict[str, Any]]:
    return handlers.audit_log(get_registry(), limit=_int_arg(params, "limit", 100))


@route("POST", r"/api/system/kill-switch")
def _kill(body: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    return handlers.set_kill_switch(get_registry(), bool(body.get("engaged", True)))


@route("POST", r"/api/system/reset")
def _reset(**_: Any) -> Dict[str, Any]:
    return handlers.reset_demo(get_registry())


@route("GET", r"/api/market/quotes")
def _quotes(**_: Any) -> List[Dict[str, Any]]:
    return handlers.market_quotes(get_registry())


# --- events -------------------------------------------------------------
@route("GET", r"/api/events/templates")
def _templates(**_: Any) -> List[Dict[str, Any]]:
    return handlers.list_templates(get_registry())


@route("GET", r"/api/events")
def _events(params: Dict[str, List[str]], **_: Any) -> List[Dict[str, Any]]:
    return handlers.list_events(get_registry(), limit=_int_arg(params, "limit", 40))


@route("POST", r"/api/events/sync")
def _events_sync(params: Dict[str, List[str]], **_: Any) -> Dict[str, Any]:
    return handlers.sync_events(get_registry(), limit=_int_arg(params, "limit", 40))


@route("POST", r"/api/events")
def _events_post(body: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    if not body.get("title"):
        raise HttpError(422, "title is required")
    return handlers.run_event_payload(get_registry(), body)


@route("GET", r"/api/events/(?P<event_id>[^/]+)")
def _event_detail(event_id: str, **_: Any) -> Dict[str, Any]:
    event = get_registry().events.get_event(event_id)
    if event is None:
        raise HttpError(404, f"Unknown event {event_id}")
    return event.model_dump(mode="json")


# --- agent --------------------------------------------------------------
@route("GET", r"/api/agent/templates")
def _agent_templates(**_: Any) -> List[Dict[str, Any]]:
    return handlers.list_templates(get_registry())


@route("POST", r"/api/agent/simulate")
def _simulate(body: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    key = str(body.get("template_key") or "")
    service = get_registry()
    if key not in service.events.template_keys():
        raise HttpError(404, f"Unknown template '{key}'")
    return handlers.simulate_event(service, key)


@route("POST", r"/api/agent/run")
def _run(body: Dict[str, Any], **_: Any) -> Dict[str, Any]:
    key = str(body.get("template_key") or "")
    service = get_registry()
    if key not in service.events.template_keys():
        raise HttpError(404, f"Unknown template '{key}'")
    return handlers.run_sync(service, template_key=key)


@route("GET", r"/api/agent/decisions")
def _decisions(params: Dict[str, List[str]], **_: Any) -> List[Dict[str, Any]]:
    return handlers.list_decisions(get_registry(), limit=_int_arg(params, "limit", 25))


@route("GET", r"/api/agent/explain/(?P<symbol>[^/]+)")
def _explain(symbol: str, **_: Any) -> Dict[str, Any]:
    return handlers.explain_symbol(get_registry(), symbol)


@route("GET", r"/api/agent/decisions/(?P<decision_id>[^/]+)")
def _decision(decision_id: str, **_: Any) -> Dict[str, Any]:
    result = handlers.get_decision(get_registry(), decision_id)
    if result is None:
        raise HttpError(404, f"Unknown decision {decision_id}")
    return result


# --- portfolio ----------------------------------------------------------
@route("GET", r"/api/portfolio/history")
def _history(params: Dict[str, List[str]], **_: Any) -> List[Dict[str, Any]]:
    return handlers.equity_curve(get_registry(), limit=_int_arg(params, "limit", 240))


@route("GET", r"/api/portfolio/trades")
def _trades(params: Dict[str, List[str]], **_: Any) -> List[Dict[str, Any]]:
    return handlers.trade_history(get_registry(), limit=_int_arg(params, "limit", 100))


@route("GET", r"/api/portfolio/positions")
def _positions(**_: Any) -> List[Dict[str, Any]]:
    return handlers.portfolio_view(get_registry())["positions"]


@route("GET", r"/api/portfolio")
def _portfolio(**_: Any) -> Dict[str, Any]:
    return handlers.portfolio_view(get_registry())


class EventraRequestHandler(BaseHTTPRequestHandler):
    server_version = "EventraDev/1.0"
    protocol_version = "HTTP/1.1"

    # --- helpers --------------------------------------------------------
    def _cors(self) -> None:
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HttpError(400, f"Invalid JSON body: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HttpError(422, "Request body must be a JSON object")
        return parsed

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if getattr(self.server, "verbose", False):
            sys.stderr.write("[eventra] " + (fmt % args) + "\n")

    # --- verbs ----------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if not path.startswith("/api"):
            self._serve_static(path)
            return

        for route_method, pattern, func in ROUTES:
            if route_method != method:
                continue
            match = pattern.match(path)
            if not match:
                continue
            try:
                kwargs: Dict[str, Any] = dict(match.groupdict())
                body = self._read_body() if method == "POST" else {}
                if body:
                    kwargs["body"] = body
                kwargs["params"] = params
                result = func(**kwargs)
                self._send_json(202 if path == "/api/agent/simulate" else 200, result)
            except HttpError as exc:
                self._send_json(exc.status, {"detail": exc.detail})
            except KeyError as exc:
                self._send_json(404, {"detail": f"Not found: {exc}"})
            except Exception as exc:  # pragma: no cover - defensive
                traceback.print_exc()
                self._send_json(500, {"detail": f"{type(exc).__name__}: {exc}"})
            return

        self._send_json(404, {"detail": f"No route for {method} {path}"})

    # --- static ---------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        if path in {"/", "/ui", "/index.html", "/ui/", "/ui/index.html"}:
            target = STATIC_DIR / "index.html"
        else:
            relative = path.lstrip("/").removeprefix("ui/")
            target = (STATIC_DIR / relative).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._send_json(403, {"detail": "Forbidden"})
                return

        if not target.exists() or not target.is_file():
            self._send_json(404, {"detail": f"Not found: {path}"})
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type = f"{content_type}; charset=utf-8"
        self._send_bytes(200, target.read_bytes(), content_type)


def serve(host: str = "127.0.0.1", port: int = 8000, verbose: bool = False) -> ThreadingHTTPServer:
    get_registry().bootstrap()
    httpd = ThreadingHTTPServer((host, port), EventraRequestHandler)
    httpd.daemon_threads = True
    httpd.verbose = verbose  # type: ignore[attr-defined]
    return httpd


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = "127.0.0.1"
    port = 8000
    verbose = "--verbose" in argv
    for index, arg in enumerate(argv):
        if arg in {"--host", "-h"} and index + 1 < len(argv):
            host = argv[index + 1]
        if arg in {"--port", "-p"} and index + 1 < len(argv):
            port = int(argv[index + 1])

    httpd = serve(host, port, verbose=verbose)
    registry = get_registry()
    print("=" * 68)
    print("  EVENTRA - From Events to Execution")
    print("=" * 68)
    print(f"  API      : http://{host}:{port}/api")
    print(f"  Terminal : http://{host}:{port}/")
    print(f"  LLM      : {registry.settings.llm_mode}"
          f" ({'Qwen ' + registry.settings.qwen_model if registry.qwen.available else 'Demo Mode - set QWEN_API_KEY'})")
    print(f"  Store    : {type(registry.repository).__name__}")
    print("  Mode     : PAPER / DEMO  (no real orders are ever sent)")
    print("=" * 68)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[eventra] shutting down")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
