from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mentat_broker.models import Decision, Offer
from mentat_broker.production_sessions import ProductionSessionManager
from mentat_broker.registry import ModelRegistry
from mentat_broker.sessions import ApprovalCoordinator
from mentat_broker.store import BrokerStore

ROOT = Path(__file__).parents[3]
REGISTRY = ROOT / "config" / "model-registry.json"
SCRIPTS = ROOT / "scripts" / "mentat"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import vast_endpoint_hardening as create_hardening  # noqa: E402
import vast_endpoint_production as lifecycle  # noqa: E402
from vast_http import VastApiError  # noqa: E402


def kimi_offer() -> Offer:
    return Offer(
        id=10,
        gpu_name="H200",
        num_gpus=8,
        gpu_ram_mb=140000,
        hourly_usd=24,
        reliability=0.995,
        verified=True,
        bw_nvlink=900,
        disk_space_gb=1000,
    )


def pending_decision(registry: ModelRegistry) -> Decision:
    model = registry.get("kimi-k2.7-code")
    return Decision(
        id="budget-before-create",
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview="Fix production code",
        prompt_digest="digest",
        task_class="large_code",
        selected_model=model.id,
        selected_model_id=model.model_id,
        fallback_chain=model.fallback_chain,
        reasons=[],
        quality_score=0.98,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=kimi_offer(),
        offer_source="live-vast",
        estimated_minutes=30,
        estimated_cost_usd=12,
        max_hourly_usd=32,
        max_total_usd=12,
        status="pending",
        metadata={
            "requirements": {
                "task_class": "large_code",
                "capabilities": ["reasoning", "coding", "tools"],
                "minimum_quality_tier": 5,
                "estimated_input_tokens": 20000,
            }
        },
    )


def test_budget_expiry_is_saved_before_paid_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelRegistry.load(REGISTRY)
    store = BrokerStore(tmp_path / "broker.sqlite3")
    decision = pending_decision(registry)
    store.save_decision(decision)
    manager = ProductionSessionManager(
        root=ROOT,
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    observed: list[tuple[str, float]] = []

    def fake_lifecycle(model, command, *extra, config_path=None):
        session = store.get_session(model.id)
        assert session is not None
        approved_until = datetime.fromisoformat(str(session["approved_until"]))
        remaining_hours = (approved_until - datetime.now(UTC)).total_seconds() / 3600
        observed.append((command, remaining_hours))
        if command == "create":
            manager.endpoint_state_path(model).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(manager, "_lifecycle", fake_lifecycle)
    approved = manager.approve(decision, accept_benchmark_cost=True)
    assert approved.status == "approved"
    assert [command for command, _hours in observed] == ["create", "warm"]
    assert all(0 < hours <= 0.51 for _command, hours in observed)
    store.close()


def test_ambiguous_workergroup_create_is_reconciled_without_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = lifecycle.load_json(
        ROOT / "infrastructure" / "vast" / "kimi-k2.7-code" / "endpoint.json"
    )
    state_path = tmp_path / "state.json"
    args = argparse.Namespace(
        accept_test_worker_cost=True,
        template_hash="template-hash",
        state=state_path,
    )
    discoveries = iter(
        [
            (None, None),
            (
                {"id": 101, "endpoint_name": config["endpoint_name"]},
                {
                    "id": 202,
                    "endpoint_id": 101,
                    "endpoint_name": config["endpoint_name"],
                },
            ),
        ]
    )
    methods: list[tuple[str, str]] = []

    monkeypatch.setenv("VAST_API_KEY", "test")
    monkeypatch.setattr(create_hardening, "_discover", lambda _key, _config: next(discoveries))

    def fake_request(method, url, api_key, payload=None, **kwargs):
        del api_key, payload, kwargs
        methods.append((method, url))
        if url.endswith("/endptjobs/"):
            return {"result": 101}
        if url.endswith("/workergroups/"):
            raise VastApiError("response lost after remote create")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(create_hardening, "request_json", fake_request)
    create_hardening.command_create(args, config)

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["endpoint_id"] == 101
    assert saved["workergroup_id"] == 202
    assert [method for method, _url in methods] == ["POST", "POST"]
    assert not any(method == "DELETE" for method, _url in methods)
