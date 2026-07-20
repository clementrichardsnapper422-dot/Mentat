from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace

import pytest

from mentat_broker.models import BenchmarkRecord, Decision, Offer
from mentat_broker.production_app import ProductionBrokerApplication
from mentat_broker.production_http import (
    LoopbackThreadingHTTPServer,
    production_handler_factory,
    production_read_json,
    set_max_body_bytes,
    write_secure_json,
)
from mentat_broker.production_sessions import ProductionSessionManager
from mentat_broker.registry import ModelRegistry
from mentat_broker.router import RoutingError
from mentat_broker.sessions import ApprovalCoordinator
from mentat_broker.store import BrokerStore
from mentat_broker.vast import VastOfferDiscovery

ROOT = Path(__file__).parents[3]
REGISTRY = ROOT / "config" / "model-registry.json"


def offer_for(model, hourly: float) -> Offer:
    return Offer(
        id=1,
        gpu_name=model.gpu_names[0],
        num_gpus=model.num_gpus,
        gpu_ram_mb=model.min_gpu_ram_mb,
        hourly_usd=hourly,
        reliability=0.995,
        verified=True,
        bw_nvlink=model.min_nvlink_bw or None,
        disk_space_gb=float(model.min_disk_gb),
    )


@pytest.fixture
def production_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MENTAT_BROKER_CLIENT_TOKEN", "client-token")
    monkeypatch.setenv("MENTAT_BROKER_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("VAST_API_KEY", "test-vast-key")
    application = ProductionBrokerApplication(ROOT, REGISTRY, tmp_path / "data")
    prices = {
        "kimi-k2.7-code": 24,
        "qwen3-coder-30b": 2,
        "deepseek-coder-v2-lite": 1,
    }
    application.offers_for = lambda model, refresh=False: [  # type: ignore[method-assign]
        offer_for(model, prices[model.id])
    ]
    yield application
    application.close()


def test_kimi_stays_primary_until_cheaper_model_is_measured(production_app) -> None:
    first = production_app.plan(
        {"prompt": "Summarize this paragraph", "requires_tools": False}
    )
    assert first.selected_model == "kimi-k2.7-code"

    for _ in range(5):
        production_app.store.add_benchmark(
            BenchmarkRecord(
                model_id="qwen3-coder-30b",
                task_class="simple",
                success=True,
                latency_ms=100,
                tokens_per_second=80,
                hourly_usd=2,
                total_cost_usd=0.1,
                quality_score=0.94,
                notes="rated production fixture",
            )
        )
    second = production_app.plan(
        {"prompt": "Summarize this paragraph", "requires_tools": False}
    )
    assert second.selected_model == "qwen3-coder-30b"
    assert second.quality_source == "measured"


def test_text_only_serverless_rejects_images(production_app) -> None:
    with pytest.raises(RoutingError, match="text-only"):
        production_app.plan(
            {"prompt": "Inspect this screenshot", "has_images": True, "requires_tools": False}
        )


def test_short_followup_keeps_previous_user_intent(production_app) -> None:
    prompt, _ = production_app.routing_prompt_from_messages(
        [
            {"role": "user", "content": "Refactor the repository and run all tests"},
            {"role": "assistant", "content": "Ready."},
            {"role": "user", "content": "go"},
        ]
    )
    assert "Refactor the repository" in prompt
    assert "Follow-up: go" in prompt


def test_fallback_must_satisfy_original_requirements(tmp_path: Path) -> None:
    registry = ModelRegistry.load(REGISTRY)
    store = BrokerStore(tmp_path / "broker.sqlite3")
    manager = ProductionSessionManager(
        root=ROOT,
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    for model_id in ("qwen3-coder-30b", "deepseek-coder-v2-lite"):
        store.upsert_session(model_id, status="ready", approved_until=expires)
    decision = Decision(
        id="high-risk",
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview="deploy production security fix",
        prompt_digest="digest",
        task_class="high_risk",
        selected_model="kimi-k2.7-code",
        selected_model_id=registry.get("kimi-k2.7-code").model_id,
        fallback_chain=["qwen3-coder-30b", "deepseek-coder-v2-lite"],
        reasons=[],
        quality_score=0.98,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=offer_for(registry.get("kimi-k2.7-code"), 24),
        offer_source="live-vast",
        estimated_minutes=30,
        estimated_cost_usd=12,
        max_hourly_usd=32,
        max_total_usd=64,
        status="approved",
        metadata={
            "requirements": {
                "task_class": "high_risk",
                "capabilities": ["reasoning", "tools"],
                "minimum_quality_tier": 5,
                "estimated_input_tokens": 32000,
            }
        },
    )
    manager.set_current_decision(decision)
    assert manager.ready_fallbacks(registry.get("kimi-k2.7-code")) == []
    store.close()


class FakeBodyHandler:
    def __init__(self, body: bytes, content_type: str = "application/json"):
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": content_type,
        }
        self.rfile = io.BytesIO(body)


def test_request_body_limit_is_enforced() -> None:
    set_max_body_bytes(10)
    with pytest.raises(ValueError, match="too large"):
        production_read_json(FakeBodyHandler(b'{"value":12345}'))
    set_max_body_bytes(1024)
    assert production_read_json(FakeBodyHandler(b'{"ok":true}')) == {"ok": True}


def test_vast_offer_query_uses_documented_ondemand_and_hardware_filters(monkeypatch) -> None:
    registry = ModelRegistry.load(REGISTRY)
    model = registry.get("kimi-k2.7-code")
    discovery = VastOfferDiscovery(api_key="test")
    captured = {}

    def fake_request(payload):
        captured.update(payload)
        return {"offers": []}

    monkeypatch.setattr(discovery, "_request", fake_request)
    discovery.search(model, registry.policy)
    assert captured["type"] == "ondemand"
    assert captured["disk_space"]["gte"] == 800
    assert captured["bw_nvlink"]["gte"] > 0
    assert captured["duration"]["gte"] == 14400


def test_loopback_http_boundary_requires_correct_tokens() -> None:
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
        return b"<html><script>const list = document.getElementById('list');</script></html>"

    handler = production_handler_factory(base_factory, ui, application)
    server = LoopbackThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=2) as response:
            assert json.loads(response.read())["service"] == "mentat-broker"
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(base + "/v1/models", timeout=2)
        assert unauthorized.value.code == 401
        request = urllib.request.Request(
            base + "/v1/models",
            headers={"Authorization": "Bearer client"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 200
        with pytest.raises(urllib.error.HTTPError) as ui_unauthorized:
            urllib.request.urlopen(base + "/ui/decisions", timeout=2)
        assert ui_unauthorized.value.code == 401
        ui_request = urllib.request.Request(
            base + "/ui/decisions",
            headers={"Authorization": "Bearer admin"},
        )
        with urllib.request.urlopen(ui_request, timeout=2) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
