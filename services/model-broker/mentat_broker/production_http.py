from __future__ import annotations

import hmac
import json
import re
import urllib.parse
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_CURRENT_MAX_BODY_BYTES = 8 * 1024 * 1024


class LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False
    request_queue_size = 64

    def __init__(self, server_address: tuple[str, int], *args: Any, **kwargs: Any):
        host = str(server_address[0]).lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("the production broker may bind only to a loopback address")
        super().__init__(server_address, *args, **kwargs)


def set_max_body_bytes(value: int) -> None:
    global _CURRENT_MAX_BODY_BYTES
    _CURRENT_MAX_BODY_BYTES = value


def production_read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    if handler.headers.get("Transfer-Encoding"):
        raise ValueError("chunked request bodies are not accepted")
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length < 0:
        raise ValueError("invalid Content-Length")
    if length > _CURRENT_MAX_BODY_BYTES:
        raise ValueError("request body is too large")
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if length and content_type != "application/json":
        raise ValueError("Content-Type must be application/json")
    raw = handler.rfile.read(length) if length else b"{}"
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


def secure_ui(base_ui: Callable[[], bytes], admin_token: str) -> bytes:
    html = base_ui().decode("utf-8")
    token_json = json.dumps(admin_token)
    html = html.replace(
        "const list = document.getElementById('list');",
        "const list = document.getElementById('list');\n"
        f"const adminToken = {token_json};",
    )
    html = html.replace(
        "headers:{'Content-Type':'application/json'}",
        "headers:{'Content-Type':'application/json','Authorization':'Bearer '+adminToken}",
    )
    html = html.replace(
        "fetch('/v1/decisions?limit=30')",
        "fetch('/v1/decisions?limit=30',{headers:{'Authorization':'Bearer '+adminToken}})",
    )
    html = html.replace(
        "function render(decision) {",
        "async function rateDecision(id, stars) {\n"
        "  const notes = prompt('Optional note about answer quality:', '') || '';\n"
        "  await action(id, 'rate', {quality_score: stars / 5, notes});\n"
        "}\n"
        "function render(decision) {",
    )
    original_actions = (
        "${pending ? `<div class=\"actions\"><button class=\"approve\" "
        "onclick=\"approveDecision('${decision.id}')\">Approve compute</button>"
        "<button class=\"reject\" onclick=\"action('${decision.id}','reject')\">"
        "Reject</button></div>` : ''}"
    )
    rated_actions = (
        "${pending ? `<div class=\"actions\"><button class=\"approve\" "
        "onclick=\"approveDecision('${decision.id}')\">Approve compute</button>"
        "<button class=\"reject\" onclick=\"action('${decision.id}','reject')\">"
        "Reject</button></div>` : decision.status === 'completed' ? "
        "(decision.rating ? `<div class=\"actions\"><span class=\"badge\">Rated "
        "${Math.round(Number(decision.rating.quality_score) * 5)}/5</span></div>` : "
        "`<div class=\"actions\"><span class=\"label\">Rate quality</span>"
        "${[1,2,3,4,5].map(star => `<button class=\"approve\" "
        "onclick=\"rateDecision('${decision.id}',${star})\">${star}★</button>`).join('')}"
        "</div>`) : ''}"
    )
    if original_actions not in html:
        raise RuntimeError("decision UI template changed; secure production patch cannot be applied")
    return html.replace(original_actions, rated_actions).encode("utf-8")


def write_secure_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def decision_payload(application: Any, decision: Any) -> dict[str, Any]:
    value = decision.as_dict()
    value["rating"] = application.store.get_rating(decision.id)
    return value


def production_handler_factory(
    base_factory: Callable[[Any], type[BaseHTTPRequestHandler]],
    base_ui: Callable[[], bytes],
    application: Any,
) -> type[BaseHTTPRequestHandler]:
    BaseHandler = base_factory(application)

    class ProductionHandler(BaseHandler):
        server_version = "MentatBroker"
        sys_version = ""

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            super().end_headers()

        def _valid_host(self) -> bool:
            raw = str(self.headers.get("Host") or "")
            host = raw.rsplit(":", 1)[0].strip("[]").lower()
            return host in {"127.0.0.1", "localhost", "::1"}

        def _valid_origin(self) -> bool:
            raw = self.headers.get("Origin")
            if not raw:
                return True
            try:
                origin = urllib.parse.urlparse(raw)
            except ValueError:
                return False
            return origin.scheme == "http" and origin.hostname in {
                "127.0.0.1",
                "localhost",
                "::1",
            }

        def _bearer(self, expected: str) -> bool:
            supplied = str(self.headers.get("Authorization") or "")
            prefix = "Bearer "
            return supplied.startswith(prefix) and hmac.compare_digest(
                supplied[len(prefix) :], expected
            )

        def _admin_authorized(self) -> bool:
            return self._bearer(application.admin_token)

        def _deny(self, status: HTTPStatus, message: str) -> None:
            write_secure_json(self, int(status), {"error": {"message": message}})

        def do_GET(self) -> None:  # noqa: N802
            if not self._valid_host():
                self._deny(HTTPStatus.BAD_REQUEST, "invalid host")
                return
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == "/health":
                write_secure_json(
                    self,
                    HTTPStatus.OK,
                    {"ok": True, "service": "mentat-broker", "version": 1},
                )
                return
            if parsed.path == "/ui/decisions":
                if not self._admin_authorized():
                    self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                    return
                body = secure_ui(base_ui, application.admin_token)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; img-src 'self'; frame-ancestors 'none'",
                )
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/v1/models":
                if not self._bearer(application.client_token):
                    self._deny(HTTPStatus.UNAUTHORIZED, "client authorization required")
                    return
                super().do_GET()
                return
            if not self._admin_authorized():
                self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                return
            if parsed.path == "/v1/decisions":
                status = query.get("status", [None])[0]
                limit = max(1, min(100, int(query.get("limit", ["50"])[0])))
                decisions = application.store.list_decisions(status=status, limit=limit)
                write_secure_json(
                    self,
                    HTTPStatus.OK,
                    {"decisions": [decision_payload(application, item) for item in decisions]},
                )
                return
            if re.fullmatch(r"/v1/decisions/[^/]+", parsed.path):
                decision_id = parsed.path.rsplit("/", 1)[-1]
                decision = application.store.get_decision(decision_id)
                if not decision:
                    self._deny(HTTPStatus.NOT_FOUND, "decision not found")
                else:
                    write_secure_json(
                        self,
                        HTTPStatus.OK,
                        decision_payload(application, decision),
                    )
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            if not self._valid_host() or not self._valid_origin():
                self._deny(HTTPStatus.BAD_REQUEST, "invalid host or origin")
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/v1/chat/completions":
                if not self._bearer(application.client_token):
                    self._deny(HTTPStatus.UNAUTHORIZED, "client authorization required")
                    return
                if not application.request_slots.acquire(blocking=False):
                    self._deny(HTTPStatus.TOO_MANY_REQUESTS, "broker concurrency limit reached")
                    return
                try:
                    super().do_POST()
                finally:
                    application.request_slots.release()
                return
            if not self._admin_authorized():
                self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                return
            rating_match = re.fullmatch(r"/v1/decisions/([^/]+)/rate", parsed.path)
            if rating_match:
                try:
                    payload = production_read_json(self)
                    result = application.store.rate_decision(
                        rating_match.group(1),
                        float(payload.get("quality_score")),
                        str(payload.get("notes") or ""),
                    )
                    write_secure_json(self, HTTPStatus.CREATED, result)
                except (TypeError, ValueError) as exc:
                    self._deny(HTTPStatus.BAD_REQUEST, str(exc))
                return
            super().do_POST()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._deny(HTTPStatus.METHOD_NOT_ALLOWED, "CORS preflight is not supported")

    return ProductionHandler
