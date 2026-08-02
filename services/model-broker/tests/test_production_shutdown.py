from __future__ import annotations

import os
import sys
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace

import pytest
from mentat_broker.production_http import (
    LoopbackThreadingHTTPServer,
    production_handler_factory,
    write_secure_json,
)
from mentat_broker.production_shutdown import with_graceful_shutdown

SCRIPTS = Path(__file__).parents[3] / "scripts" / "mentat"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from broker_shutdown import process_exists  # noqa: E402


def test_process_exists_observes_current_process_without_terminating_it() -> None:
    assert process_exists(os.getpid()) is True
    assert process_exists(-1) is False


def test_authenticated_shutdown_stops_the_server_loop() -> None:
    application = SimpleNamespace(
        client_token="client",
        admin_token="admin",
        request_slots=threading.BoundedSemaphore(1),
    )

    def base_factory(_application):
        class Base(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def do_GET(self):  # noqa: N802
                write_secure_json(self, HTTPStatus.OK, {"ok": True})

            def do_POST(self):  # noqa: N802
                write_secure_json(self, HTTPStatus.OK, {"ok": True})

        return Base

    def ui() -> bytes:
        return b"<html></html>"

    authenticated = production_handler_factory(base_factory, ui, application)
    handler = with_graceful_shutdown(authenticated)
    server = LoopbackThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/admin/shutdown"
    try:
        unauthorized = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(unauthorized, timeout=2)
        assert error.value.code == 401

        authorized = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Authorization": "Bearer admin",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(authorized, timeout=2) as response:
            assert response.status == 202
        thread.join(timeout=3)
        assert not thread.is_alive()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
