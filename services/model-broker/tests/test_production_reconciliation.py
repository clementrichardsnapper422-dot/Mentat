from __future__ import annotations

import json
from pathlib import Path

import pytest
from mentat_broker.production_sessions import ProductionSessionManager
from mentat_broker.registry import ModelRegistry
from mentat_broker.sessions import ApprovalCoordinator, SessionError
from mentat_broker.store import BrokerStore

ROOT = Path(__file__).parents[3]
REGISTRY = ROOT / "config" / "model-registry.json"


def manager_at(tmp_path: Path) -> tuple[ProductionSessionManager, BrokerStore]:
    registry = ModelRegistry.load(REGISTRY)
    store = BrokerStore(tmp_path / "broker.sqlite3")
    manager = ProductionSessionManager(
        root=ROOT,
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    return manager, store


def test_missing_remote_resources_remove_stale_local_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, store = manager_at(tmp_path)
    model = manager.registry.get("kimi-k2.7-code")
    state_path = manager.endpoint_state_path(model)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"endpoint_id": 101, "workergroup_id": 202}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        manager,
        "_status_output",
        lambda _model, _config: {"endpoint": None, "workergroup": None},
    )
    assert manager._reconcile_saved_state(model, manager.endpoint_config_path(model)) is False
    assert not state_path.exists()
    store.close()


def test_remote_id_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, store = manager_at(tmp_path)
    model = manager.registry.get("kimi-k2.7-code")
    state_path = manager.endpoint_state_path(model)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"endpoint_id": 101, "workergroup_id": 202}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        manager,
        "_status_output",
        lambda _model, _config: {
            "endpoint": {"id": 999},
            "workergroup": {"id": 202},
        },
    )
    with pytest.raises(SessionError, match="does not match"):
        manager._reconcile_saved_state(model, manager.endpoint_config_path(model))
    assert state_path.exists()
    store.close()
