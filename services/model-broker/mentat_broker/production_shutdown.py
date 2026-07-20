from __future__ import annotations

import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from .production_http import write_secure_json


def with_graceful_shutdown(
    base_handler: type[BaseHTTPRequestHandler],
) -> type[BaseHTTPRequestHandler]:
    class GracefulShutdownHandler(base_handler):
        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/v1/admin/shutdown":
                super().do_POST()
                return
            if not self._valid_host() or not self._valid_origin():
                self._deny(HTTPStatus.BAD_REQUEST, "invalid host or origin")
                return
            if not self._admin_authorized():
                self._deny(HTTPStatus.UNAUTHORIZED, "admin authorization required")
                return
            write_secure_json(
                self,
                HTTPStatus.ACCEPTED,
                {"accepted": True, "message": "broker shutdown and endpoint cooling started"},
            )
            self.close_connection = True
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return GracefulShutdownHandler
