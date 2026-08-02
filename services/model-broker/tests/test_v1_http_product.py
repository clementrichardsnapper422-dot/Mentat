import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

from mentat_broker.production_http import LoopbackThreadingHTTPServer
from mentat_broker.v1_http import v1_handler_factory


class BaseHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_GET(self):  # noqa: N802
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        self.send_error(404)


class Store:
    def __init__(self):
        self.session = {
            "model_id": "kimi/model",
            "status": "ready",
            "endpoint_url": "http://127.0.0.1:9999/v1",
            "hourly_usd": 2.5,
            "offer": {},
            "decision_id": "decision-1",
            "started_at": "2026-08-01T20:00:00+00:00",
            "last_used_at": "2026-08-01T20:10:00+00:00",
            "approved_until": "2026-08-01T21:00:00+00:00",
            "error": None,
        }

    def list_sessions(self):
        return [dict(self.session)]

    def get_session(self, model_id):
        return dict(self.session) if model_id == self.session["model_id"] else None


class Sessions:
    def __init__(self, store):
        self.store = store
        self.cooled = []

    def cool_now(self, model_id):
        self.cooled.append(model_id)
        self.store.session["status"] = "cooled"
        return dict(self.store.session)


class Runtime:
    @staticmethod
    def status():
        return {
            "release": {"production_ready": False, "pending": [], "gates": []},
            "spend": {
                "kill_switch": False,
                "active_reserved_usd": 0,
                "today_exposure_usd": 0,
                "month_exposure_usd": 0,
                "recent_events": [],
            },
            "executions": [],
            "startup_recovery_plan": [],
        }


class Application:
    admin_token = "admin-test"
    client_token = "client-test"

    def __init__(self):
        self.store = Store()
        self.sessions = Sessions(self.store)
        self.v1 = Runtime()


def handler_factory(_application):
    return BaseHandler


def base_ui():
    return b"<html></html>"


def request_json(url, *, method="GET", token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            **({"Authorization": f"Bearer {token}"} if token else {}),
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_active_compute_requires_admin_and_cools_real_saved_session():
    application = Application()
    handler = v1_handler_factory(handler_factory, base_ui, application)
    server = LoopbackThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        try:
            request_json(base + "/v1/compute")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("active compute was readable without admin authority")

        status, payload = request_json(
            base + "/v1/compute", token=application.admin_token
        )
        assert status == 200
        assert payload["active_compute"][0]["model_id"] == "kimi/model"
        assert payload["active_compute"][0]["hourly_usd"] == 2.5
        assert "endpoint_url" not in payload["active_compute"][0]

        model_id = urllib.parse.quote("kimi/model", safe="")
        status, payload = request_json(
            base + f"/v1/compute/{model_id}/cool",
            method="POST",
            token=application.admin_token,
            body={},
        )
        assert status == 200
        assert payload == {
            "model_id": "kimi/model",
            "status": "cooled",
            "cooling_requested": True,
        }
        assert application.sessions.cooled == ["kimi/model"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
