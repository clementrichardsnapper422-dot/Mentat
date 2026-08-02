from __future__ import annotations

import json
import threading
import urllib.request
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mentat_broker import server as broker_server
from mentat_broker.models import Offer
from mentat_broker.production_app import ProductionBrokerApplication
from mentat_broker.production_http import (
    LoopbackThreadingHTTPServer,
    production_handler_factory,
)

ROOT = Path(__file__).parents[3]
REGISTRY = ROOT / "config" / "model-registry.json"


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, _format, *_args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append(payload)
        content = "OK" if int(payload.get("max_tokens") or 0) == 1 else "Mentat integration online"
        body = json.dumps(
            {
                "id": "chatcmpl-local-test",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                },
            }
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_authenticated_no_spend_chat_proxy_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeOpenAIHandler.requests = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_base = f"http://127.0.0.1:{upstream.server_address[1]}/v1"

    monkeypatch.setenv("MENTAT_BROKER_CLIENT_TOKEN", "client-token")
    monkeypatch.setenv("MENTAT_BROKER_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("VAST_API_KEY", "infrastructure-only-test-key")
    monkeypatch.setenv("MENTAT_ENDPOINT_KIMI_K2_7_CODE", upstream_base)

    application = ProductionBrokerApplication(ROOT, REGISTRY, tmp_path / "data")
    model = application.registry.get("kimi-k2.7-code")
    offer = Offer(
        id=50,
        gpu_name="H200",
        num_gpus=8,
        gpu_ram_mb=140000,
        hourly_usd=24,
        reliability=0.995,
        verified=True,
        bw_nvlink=900,
        disk_space_gb=1000,
    )
    now = datetime.now(UTC)
    application.store.upsert_session(
        model.id,
        status="ready",
        endpoint_url=upstream_base,
        hourly_usd=offer.hourly_usd,
        offer=offer,
        decision_id="existing-approved-session",
        started_at=now.isoformat(),
        last_used_at=now.isoformat(),
        approved_until=(now + timedelta(minutes=30)).isoformat(),
    )

    handler = production_handler_factory(
        broker_server.make_handler,
        broker_server._decision_ui,
        application,
    )
    broker = LoopbackThreadingHTTPServer(("127.0.0.1", 0), handler)
    broker_thread = threading.Thread(target=broker.serve_forever, daemon=True)
    broker_thread.start()
    broker_base = f"http://127.0.0.1:{broker.server_address[1]}"

    try:
        models_request = urllib.request.Request(
            broker_base + "/v1/models",
            headers={"Authorization": "Bearer client-token"},
        )
        with urllib.request.urlopen(models_request, timeout=5) as response:
            models = json.loads(response.read().decode("utf-8"))
        assert [item["id"] for item in models["data"]] == ["mentat-auto"]

        body = json.dumps(
            {
                "model": "mentat-auto",
                "messages": [{"role": "user", "content": "Explain this architecture"}],
                "max_tokens": 128,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            broker_base + "/v1/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer client-token",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            decision_id = response.headers["X-Mentat-Decision-Id"]
            assert response.headers["X-Mentat-Model"] == "kimi-k2.7-code"
            assert decision_id
        assert result["choices"][0]["message"]["content"] == "Mentat integration online"
        assert len(FakeOpenAIHandler.requests) == 2
        assert FakeOpenAIHandler.requests[0]["max_tokens"] == 1
        assert FakeOpenAIHandler.requests[1]["model"] == model.model_id
        decision = application.store.get_decision(decision_id)
        assert decision is not None
        summary = application.store.benchmark_summary(model.id, decision.task_class)
        assert summary["runtime_samples"] == 1
    finally:
        broker.shutdown()
        broker.server_close()
        broker_thread.join(timeout=2)
        application.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=2)
