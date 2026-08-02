"""Authenticated local HTTP surface for the Mentat 1.0 control plane."""

from __future__ import annotations

import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable

from .control_ui import render_control_center
from .production_http import (
    production_handler_factory,
    production_read_json,
    write_secure_json,
)


def v1_handler_factory(
    base_factory: Callable[[Any], type[BaseHTTPRequestHandler]],
    base_ui: Callable[[], bytes],
    application: Any,
) -> type[BaseHTTPRequestHandler]:
    ProductionHandler = production_handler_factory(base_factory, base_ui, application)

    class MentatV1Handler(ProductionHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in {
                "/ui/control",
                "/v1/status",
                "/v1/release",
                "/v1/spend",
                "/v1/executions",
            }:
                super().do_GET()
                return
            if not self._valid_host():
                self._deny(HTTPStatus.BAD_REQUEST, "invalid host")
                return
            if not self._admin_authorized():
                self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                return
            if parsed.path == "/ui/control":
                body = render_control_center(application.admin_token)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                )
                self.end_headers()
                self.wfile.write(body)
                return
            status = application.v1.status()
            if parsed.path == "/v1/status":
                payload = status
            elif parsed.path == "/v1/release":
                payload = status["release"]
            elif parsed.path == "/v1/spend":
                payload = status["spend"]
            else:
                payload = {
                    "executions": status["executions"],
                    "startup_recovery_plan": status["startup_recovery_plan"],
                }
            write_secure_json(self, HTTPStatus.OK, payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in {"/v1/control/kill-switch", "/v1/analyze"}:
                super().do_POST()
                return
            if not self._valid_host() or not self._valid_origin():
                self._deny(HTTPStatus.BAD_REQUEST, "invalid host or origin")
                return
            if not self._admin_authorized():
                self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                return
            try:
                payload = production_read_json(self)
                if parsed.path == "/v1/control/kill-switch":
                    if not isinstance(payload.get("enabled"), bool):
                        raise ValueError("enabled must be a boolean")
                    result = application.v1.set_kill_switch(
                        bool(payload["enabled"]),
                        reason=str(payload.get("reason") or ""),
                        actor="desktop-admin",
                    )
                else:
                    result = application.v1.analyze_task(
                        str(payload.get("prompt") or ""),
                        input_tokens=int(payload.get("input_tokens") or 0),
                        reserved_output_tokens=int(payload.get("reserved_output_tokens") or 4096),
                        tool_names=[str(value) for value in payload.get("tool_names", [])],
                        repository_files=int(payload.get("repository_files") or 0),
                        attachment_bytes=int(payload.get("attachment_bytes") or 0),
                        has_images=bool(payload.get("has_images", False)),
                        routing_mode=str(payload.get("routing_mode") or "balanced"),
                        maximum_total_cost_usd=float(
                            payload.get("maximum_total_cost_usd")
                            or application.registry.policy.max_total_usd
                        ),
                        maximum_latency_ms=int(payload.get("maximum_latency_ms") or 1_800_000),
                    )
                write_secure_json(self, HTTPStatus.OK, result)
            except (TypeError, ValueError) as exc:
                self._deny(HTTPStatus.BAD_REQUEST, str(exc))

    return MentatV1Handler
