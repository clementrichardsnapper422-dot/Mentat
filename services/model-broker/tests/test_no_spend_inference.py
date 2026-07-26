from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
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
TESTING = ROOT / "scripts" / "mentat" / "testing"
if str(TESTING) not in sys.path:
    sys.path.insert(0, str(TESTING))

from fake_openai import start_fake_openai  # noqa: E402

REGISTRY = ROOT / "config" / "model-registry.json"


def start_production_broker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    upstream, upstream_thread = start_fake_openai()
    upstream_base = f"http://127.0.0.1:{upstream.server_address[1]}/v1"
    monkeypatch.setenv("MENTAT_BROKER_CLIENT_TOKEN", "client-token")
    monkeypatch.setenv("MENTAT_BROKER_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("VAST_API_KEY", "test-vast-key")
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
    return application, broker, broker_thread, upstream, upstream_thread, broker_base


def stop_servers(application, broker, broker_thread, upstream, upstream_thread) -> None:
    broker.shutdown()
    broker.server_close()
    broker_thread.join(timeout=2)
    application.close()
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=2)


def broker_chat(base: str, content: str, **extra):
    payload = {
        "model": "mentat-auto",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 128,
        "stream": False,
        **extra,
    }
    request = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer client-token",
            "Content-Type": "application/json",
        },
    )
    return urllib.request.urlopen(request, timeout=10)


def test_json_completion_and_runtime_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with broker_chat(base, "Explain this architecture") as response:
            result = json.loads(response.read().decode("utf-8"))
            decision_id = response.headers["X-Mentat-Decision-Id"]
        assert result["choices"][0]["message"]["content"] == "Mentat no-spend inference online"
        decision = application.store.get_decision(decision_id)
        assert decision is not None and decision.status == "completed"
        summary = application.store.benchmark_summary(decision.selected_model, decision.task_class)
        assert summary["runtime_samples"] == 1
        assert upstream.state.requests[-1]["model"] == decision.selected_model_id
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_streaming_completion_is_proxied_without_buffering_contract_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with broker_chat(base, "[[stream]]", stream=True) as response:
            body = response.read().decode("utf-8")
            decision_id = response.headers["X-Mentat-Decision-Id"]
            assert response.headers["Content-Type"].startswith("text/event-stream")
        assert "data: [DONE]" in body
        assert "Mentat" in body and "online" in body
        decision = application.store.get_decision(decision_id)
        assert decision is not None and decision.status == "completed"
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_tool_call_payload_reaches_openclaw_compatible_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write a test file",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]
    try:
        with broker_chat(base, "[[tool]]", tools=tools) as response:
            result = json.loads(response.read().decode("utf-8"))
        call = result["choices"][0]["message"]["tool_calls"][0]
        assert call["function"]["name"] == "write_file"
        assert json.loads(call["function"]["arguments"])["value"] == "from-fake-openai"
        assert upstream.state.requests[-1]["tools"] == tools
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_context_rejection_is_returned_as_broker_error_without_success_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with pytest.raises(urllib.error.HTTPError) as failure:
            broker_chat(base, "[[context_error]]")
        assert failure.value.code == 409
        payload = json.loads(failure.value.read().decode("utf-8"))
        assert "maximum context length" in payload["error"]["message"]
        assert application.store.list_benchmarks(10) == []
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_upstream_outage_fails_without_recording_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with pytest.raises(urllib.error.HTTPError) as failure:
            broker_chat(base, "[[server_error]]")
        assert failure.value.code == 409
        payload = json.loads(failure.value.read().decode("utf-8"))
        assert "all approved model endpoints failed" in payload["error"]["message"]
        assert application.store.list_benchmarks(10) == []
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_malformed_http_200_is_failed_evidence_not_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with pytest.raises(urllib.error.HTTPError) as failure:
            broker_chat(base, "[[malformed]]")
        assert failure.value.code == 409
        payload = json.loads(failure.value.read().decode("utf-8"))
        assert "malformed completion JSON" in payload["error"]["message"]
        benchmarks = application.store.list_benchmarks(10)
        assert len(benchmarks) == 1
        assert benchmarks[0]["success"] is False
        decision_id = payload["error"]["decision_id"]
        decision = application.store.get_decision(decision_id)
        assert decision is not None and decision.status == "failed"
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_malformed_tool_call_is_failed_evidence_not_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with pytest.raises(urllib.error.HTTPError) as failure:
            broker_chat(base, "[[malformed_tool]]")
        assert failure.value.code == 409
        payload = json.loads(failure.value.read().decode("utf-8"))
        assert "tool call is invalid" in payload["error"]["message"]
        benchmarks = application.store.list_benchmarks(10)
        assert len(benchmarks) == 1
        assert benchmarks[0]["success"] is False
        decision = application.store.get_decision(payload["error"]["decision_id"])
        assert decision is not None and decision.status == "failed"
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)


def test_invalid_usage_telemetry_is_ignored_before_success_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = start_production_broker(tmp_path, monkeypatch)
    application, broker, broker_thread, upstream, upstream_thread, base = components
    try:
        with broker_chat(base, "[[invalid_usage]]") as response:
            result = json.loads(response.read().decode("utf-8"))
            decision_id = response.headers["X-Mentat-Decision-Id"]
        assert result["choices"][0]["message"]["content"] == "Mentat no-spend inference online"
        decision = application.store.get_decision(decision_id)
        assert decision is not None and decision.status == "completed"
        benchmarks = application.store.list_benchmarks(10)
        assert len(benchmarks) == 1
        assert benchmarks[0]["success"] is True
        assert benchmarks[0]["tokens_per_second"] is None
    finally:
        stop_servers(application, broker, broker_thread, upstream, upstream_thread)
