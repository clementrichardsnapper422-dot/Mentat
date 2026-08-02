from datetime import UTC, datetime

import pytest

from mentat_broker.authority import AuthorityError, BrokerAuthority
from mentat_broker.contracts import (
    BackendKind,
    ExecutionState,
    ProviderLifecycle,
    ProviderResource,
)
from mentat_broker.models import Decision, ModelSpec, Offer
from mentat_broker.production import AuthoritativeProductionSessionManager
from mentat_broker.runtime import MentatV1Runtime
from mentat_broker.spend import BudgetPolicy, SpendError


def model(*, capabilities: set[str] | None = None) -> ModelSpec:
    return ModelSpec(
        id="qwen",
        display_name="Qwen",
        model_id="Qwen/Qwen-Test",
        provider="vast",
        enabled=True,
        quality_tier=4,
        bootstrap_quality={"code": 0.9},
        capabilities=capabilities or {"reasoning", "coding", "tools"},
        task_classes={"code"},
        context_tokens=65_536,
        num_gpus=1,
        min_gpu_ram_mb=80_000,
        gpu_names=["H100"],
        max_hourly_usd=8,
        endpoint_config="infrastructure/vast/qwen/endpoint.json",
        state_name="qwen.json",
        fallback_chain=[],
        default_minutes={"code": 25},
        min_disk_gb=100,
    )


def decision(identifier: str = "decision-1", *, status: str = "pending") -> Decision:
    offer = Offer(
        id=1,
        gpu_name="H100",
        num_gpus=1,
        gpu_ram_mb=80_000,
        hourly_usd=2,
        reliability=0.999,
        verified=True,
        disk_space_gb=100,
    )
    return Decision(
        id=identifier,
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview="Fix the repository bug",
        prompt_digest="abc",
        task_class="code",
        selected_model="qwen",
        selected_model_id="Qwen/Qwen-Test",
        fallback_chain=[],
        reasons=[],
        quality_score=0.9,
        quality_source="measured",
        benchmark_samples=10,
        offer=offer,
        offer_source="live-vast",
        estimated_minutes=25,
        estimated_cost_usd=1,
        max_hourly_usd=8,
        max_total_usd=8,
        status=status,  # type: ignore[arg-type]
        metadata={
            "requirements": {
                "task_class": "code",
                "capabilities": ["reasoning", "coding", "tools"],
                "estimated_input_tokens": 2_000,
            }
        },
    )


def runtime(tmp_path) -> MentatV1Runtime:
    return MentatV1Runtime(
        tmp_path,
        budget_policy=BudgetPolicy(
            maximum_hourly_usd=8,
            maximum_session_usd=8,
            maximum_daily_usd=20,
            maximum_monthly_usd=100,
            maximum_retry_usd=2,
            maximum_fallback_usd=4,
            maximum_exploration_usd=1,
            one_paid_session=True,
        ),
    )


def test_single_authority_controls_route_spend_and_provider_state(tmp_path):
    app = runtime(tmp_path)
    authority = BrokerAuthority(app)
    route = decision()
    selected = model()
    try:
        record = authority.register_decision(route, selected)
        assert record.state == ExecutionState.AWAITING_APPROVAL
        assert route.metadata["authority_owner"] == "mentat-v1"

        grant = authority.prepare_paid_provider(
            route,
            selected,
            hourly_usd=2,
            maximum_session_hours=4,
        )
        authority.verify_provider_mutation(
            grant,
            decision_id=route.id,
            model_id=selected.id,
            hourly_usd=2,
        )
        acquiring = app.executions.get(record.execution_id)
        assert acquiring is not None
        assert acquiring.state == ExecutionState.ACQUIRING

        resource = ProviderResource(
            backend=BackendKind.VAST_SERVERLESS,
            resource_id="vast-serverless:10:20",
            lifecycle=ProviderLifecycle.WARMING,
            model_id=selected.id,
            hourly_usd=2,
            created_at=datetime.now(UTC).isoformat(),
            last_observed_at=datetime.now(UTC).isoformat(),
            endpoint_url="https://openai.vast.ai/test/v1",
        )
        authority.provider_acquired(grant, resource)
        authority.provider_ready(route, selected)
        assert authority.assert_ready(selected.id, route).state == ExecutionState.READY

        reused = decision("decision-2", status="approved")
        assert authority.register_decision(reused, selected).execution_id == record.execution_id
        assert reused.metadata["authority_reused_execution"] is True

        authority.provider_cooled(selected.id, reason="test complete")
        cooled = app.executions.get(record.execution_id)
        assert cooled is not None
        assert cooled.state == ExecutionState.COOLED
        reservation = app.spend.get(grant.reservation_id)
        assert reservation is not None
        assert reservation.state == "reserved"
    finally:
        app.close()


def test_vast_adapter_refuses_mutation_without_authority_grant(tmp_path):
    app = runtime(tmp_path)
    authority = BrokerAuthority(app)
    route = decision()
    selected = model()
    authority.register_decision(route, selected)
    manager = AuthoritativeProductionSessionManager.__new__(
        AuthoritativeProductionSessionManager
    )
    manager.registry = type("Registry", (), {"get": lambda self, _model_id: selected})()
    manager._authority = authority
    try:
        with pytest.raises(AuthorityError, match="grant is required"):
            manager.approve(
                route,
                accept_benchmark_cost=True,
                authority_grant=None,
            )
    finally:
        app.close()


def test_kill_switch_blocks_provider_authority_before_vast_mutation(tmp_path):
    app = runtime(tmp_path)
    authority = BrokerAuthority(app)
    route = decision()
    selected = model()
    try:
        authority.register_decision(route, selected)
        app.set_kill_switch(True, reason="incident", actor="pytest")
        with pytest.raises(SpendError, match="kill switch"):
            authority.prepare_paid_provider(
                route,
                selected,
                hourly_usd=2,
                maximum_session_hours=4,
            )
        waiting = app.executions.get(route.id)
        assert waiting is not None
        assert waiting.state == ExecutionState.AWAITING_APPROVAL
    finally:
        app.close()


def test_authority_rejects_incompatible_legacy_route(tmp_path):
    app = runtime(tmp_path)
    authority = BrokerAuthority(app)
    try:
        with pytest.raises(AuthorityError, match="missing required capabilities"):
            authority.register_decision(
                decision(),
                model(capabilities={"reasoning", "coding"}),
            )
        assert app.executions.list(limit=10) == []
    finally:
        app.close()
