from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest

from mentat_broker.models import Decision, Offer
from mentat_broker.registry import ModelRegistry
from mentat_broker.safety import (
    SafeEndpointSessionManager,
    safe_read_json,
    secure_decision_ui,
)
from mentat_broker.sessions import ApprovalCoordinator
from mentat_broker.store import BrokerStore


class FakeHandler:
    def __init__(self, body: bytes, content_type: str):
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": content_type,
        }
        self.rfile = io.BytesIO(body)


def load_registry() -> ModelRegistry:
    root = Path(__file__).parents[3]
    return ModelRegistry.load(root / "config" / "model-registry.json")


def make_decision(model_id: str, hourly: float = 8.0) -> Decision:
    model = load_registry().get(model_id)
    return Decision(
        id=f"decision-{model_id}",
        created_at="2026-01-01T00:00:00+00:00",
        prompt_preview="Production code task",
        prompt_digest="digest",
        task_class="code" if model_id != "kimi-k2.7-code" else "high_risk",
        selected_model=model.id,
        selected_model_id=model.model_id,
        fallback_chain=model.fallback_chain,
        reasons=[],
        quality_score=0.95,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=Offer(1, model.gpu_names[0], model.num_gpus, model.min_gpu_ram_mb, hourly, 0.995, True),
        offer_source="live-vast",
        estimated_minutes=20,
        estimated_cost_usd=hourly / 3,
        max_hourly_usd=32,
        max_total_usd=4,
    )


def test_json_posts_require_application_json() -> None:
    with pytest.raises(ValueError, match="Content-Type"):
        safe_read_json(FakeHandler(b'{"ok": true}', "text/plain"))
    assert safe_read_json(FakeHandler(b'{"ok": true}', "application/json")) == {"ok": True}


def test_decision_ui_injects_approval_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import mentat_broker.safety as safety

    monkeypatch.setattr(safety, "_CURRENT_APPROVAL_TOKEN", "private-token")
    html = secure_decision_ui().decode("utf-8")
    assert "private-token" in html
    assert "_approval_token" in html or "X-Mentat-Approval-Token" in html


def test_approval_window_is_capped_by_total_budget(tmp_path: Path) -> None:
    registry = load_registry()
    store = BrokerStore(tmp_path / "broker.db")
    manager = SafeEndpointSessionManager(
        root=Path(__file__).parents[3],
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    selected = registry.get("qwen3-coder-30b")
    manager.endpoint_state_path(selected).write_text("{}", encoding="utf-8")
    manager._lifecycle = lambda *args, **kwargs: None  # type: ignore[method-assign]
    decision = make_decision(selected.id)
    store.save_decision(decision)

    manager.approve(decision, accept_benchmark_cost=False)
    session = store.get_session(selected.id)
    assert session is not None
    approved_until = datetime.fromisoformat(session["approved_until"])
    started_at = datetime.fromisoformat(session["started_at"])
    assert (approved_until - started_at).total_seconds() <= 30 * 60 + 1


def test_second_paid_session_is_blocked(tmp_path: Path) -> None:
    registry = load_registry()
    store = BrokerStore(tmp_path / "broker.db")
    manager = SafeEndpointSessionManager(
        root=Path(__file__).parents[3],
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    store.upsert_session(
        "kimi-k2.7-code",
        status="ready",
        endpoint_url="https://example.invalid/v1",
        approved_until="2099-01-01T00:00:00+00:00",
    )
    decision = make_decision("qwen3-coder-30b", hourly=2.0)
    store.save_decision(decision)

    with pytest.raises(RuntimeError, match="paid-session limit"):
        manager.approve(decision, accept_benchmark_cost=True)
