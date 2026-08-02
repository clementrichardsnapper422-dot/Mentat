import pytest
from mentat_broker.contracts import (
    BackendKind,
    ExecutionState,
    ProviderLifecycle,
    ProviderResource,
    utc_now,
)
from mentat_broker.execution import ExecutionError, ExecutionStore


def resource(identifier="remote-1"):
    return ProviderResource(
        backend=BackendKind.VAST_SERVERLESS,
        resource_id=identifier,
        lifecycle=ProviderLifecycle.WARMING,
        model_id="kimi",
        hourly_usd=2,
        created_at=utc_now(),
        last_observed_at=utc_now(),
    )


def advance_to_acquiring(store):
    record = store.create(
        execution_id="e1",
        decision_id="d1",
        model_id="kimi",
        backend=BackendKind.VAST_SERVERLESS,
    )
    for state in (
        ExecutionState.PLANNED,
        ExecutionState.AWAITING_APPROVAL,
        ExecutionState.APPROVED,
        ExecutionState.RESERVING,
        ExecutionState.ACQUIRING,
    ):
        record = store.transition(
            "e1",
            state,
            actor="test",
            expected_version=record.version,
        )
    return record


def test_illegal_transition_and_stale_version_fail(tmp_path):
    store = ExecutionStore(tmp_path / "execution.sqlite3")
    record = store.create(
        execution_id="e1",
        decision_id="d1",
        model_id="kimi",
        backend=BackendKind.VAST_SERVERLESS,
    )
    with pytest.raises(ExecutionError, match="illegal"):
        store.transition("e1", ExecutionState.RUNNING, actor="test")
    updated = store.transition(
        "e1",
        ExecutionState.PLANNED,
        actor="test",
        expected_version=record.version,
    )
    with pytest.raises(ExecutionError, match="version changed"):
        store.transition(
            "e1",
            ExecutionState.CANCELLED,
            actor="test",
            expected_version=record.version,
        )
    assert updated.version == record.version + 1


def test_resource_identity_is_unique_and_startup_recovery_never_retries(tmp_path):
    store = ExecutionStore(tmp_path / "execution.sqlite3")
    record = advance_to_acquiring(store)
    record = store.attach_resource(
        "e1",
        resource(),
        actor="test",
        expected_version=record.version,
    )
    store.transition(
        "e1",
        ExecutionState.WARMING,
        actor="test",
        expected_version=record.version,
        provider_lifecycle=ProviderLifecycle.WARMING,
    )
    plan = store.startup_recovery_plan()
    assert plan[0]["action"] == "observe_then_cool_or_reconcile"
    assert plan[0]["new_paid_mutation_allowed"] is False

    store.create(
        execution_id="e2",
        decision_id="d2",
        model_id="kimi",
        backend=BackendKind.VAST_SERVERLESS,
    )
    with pytest.raises(ExecutionError, match="already owned"):
        store.attach_resource("e2", resource(), actor="test")
