"""Single production authority for Mentat routing, spend, and execution state.

The established production router and Vast session manager remain compatibility
adapters. They may propose a route or perform a provider operation, but no paid
provider mutation or inference route is valid unless this authority has accepted
and recorded it first.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .contracts import (
    ApprovalLease,
    BackendKind,
    ExecutionState,
    ProviderLifecycle,
    ProviderResource,
)
from .execution import ExecutionRecord
from .models import Decision, ModelSpec
from .runtime import MentatV1Runtime


class AuthorityError(RuntimeError):
    """Raised when a route or provider mutation bypasses Mentat authority."""


@dataclass(frozen=True)
class ProviderMutationGrant:
    """In-process proof that paid exposure was authorized before mutation."""

    decision_id: str
    execution_id: str
    model_id: str
    backend: BackendKind
    hourly_usd: float
    worst_case_usd: float
    expires_at: str
    reservation_id: str
    lease: ApprovalLease


class BrokerAuthority:
    """The only production component allowed to authorize paid compute."""

    ACTIVE_STATES = {
        ExecutionState.APPROVED,
        ExecutionState.RESERVING,
        ExecutionState.ACQUIRING,
        ExecutionState.WARMING,
        ExecutionState.READY,
        ExecutionState.RUNNING,
        ExecutionState.AMBIGUOUS,
        ExecutionState.RECONCILING,
        ExecutionState.COOLING,
    }

    def __init__(self, runtime: MentatV1Runtime) -> None:
        self.runtime = runtime

    @staticmethod
    def backend_for(model: ModelSpec) -> BackendKind:
        if model.provider == "vast":
            return BackendKind.VAST_SERVERLESS
        if model.provider == "external":
            return BackendKind.LOCAL
        raise AuthorityError(f"unsupported production provider: {model.provider}")

    def register_decision(self, decision: Decision, model: ModelSpec) -> ExecutionRecord:
        """Accept a compatibility route and make it an authoritative execution."""

        self._validate_route(decision, model)
        backend = self.backend_for(model)
        reusable = self.active_execution_for_model(model.id, include_cooled=True)
        if decision.status == "approved":
            if reusable is None or reusable.state != ExecutionState.READY:
                raise AuthorityError(
                    "legacy session claims approval without a ready Mentat authority record"
                )
            self._bind_decision_metadata(decision, reusable, reused=True)
            return reusable
        if reusable is not None and reusable.state == ExecutionState.COOLED:
            self._bind_decision_metadata(decision, reusable, reused=True)
            return reusable

        existing = self.runtime.executions.get(decision.id)
        if existing is None:
            existing = self.runtime.executions.create(
                execution_id=decision.id,
                decision_id=decision.id,
                model_id=model.id,
                backend=backend,
                metadata={
                    "authority": "mentat-v1",
                    "candidate_generator": "legacy-production-router",
                    "task_class": decision.task_class,
                    "prompt_digest": decision.prompt_digest,
                },
            )
            existing = self.runtime.executions.transition(
                existing.execution_id,
                ExecutionState.PLANNED,
                actor="mentat-v1-authority",
                expected_version=existing.version,
                detail={"route_accepted": True},
            )
            existing = self.runtime.executions.transition(
                existing.execution_id,
                ExecutionState.AWAITING_APPROVAL,
                actor="mentat-v1-authority",
                expected_version=existing.version,
                detail={"manual_approval_required": True},
            )
        self._bind_decision_metadata(decision, existing, reused=False)
        return existing

    def prepare_no_spend_provider(self, decision: Decision, model: ModelSpec) -> ExecutionRecord:
        """Authorize a non-paid provider path through the same state authority."""

        if model.provider != "external":
            raise AuthorityError("no-spend provider authorization is external-only")
        record = self._execution_for_decision(decision)
        if record.state != ExecutionState.AWAITING_APPROVAL:
            raise AuthorityError(
                f"no-spend provider cannot start from {record.state.value}"
            )
        for state in (
            ExecutionState.APPROVED,
            ExecutionState.RESERVING,
            ExecutionState.ACQUIRING,
        ):
            record = self.runtime.executions.transition(
                record.execution_id,
                state,
                actor="mentat-v1-authority",
                expected_version=record.version,
                detail={"paid_exposure": False},
            )
        return record

    def prepare_paid_provider(
        self,
        decision: Decision,
        model: ModelSpec,
        *,
        hourly_usd: float,
        maximum_session_hours: float,
    ) -> ProviderMutationGrant:
        """Reserve worst-case exposure before the Vast adapter may mutate state."""

        backend = self.backend_for(model)
        if backend != BackendKind.VAST_SERVERLESS:
            raise AuthorityError("paid provider grants are Vast Serverless-only in 1.0")
        record = self._execution_for_decision(decision)
        if record.state not in {ExecutionState.AWAITING_APPROVAL, ExecutionState.COOLED}:
            raise AuthorityError(
                f"paid provider cannot start from {record.state.value}"
            )
        if hourly_usd <= 0:
            raise AuthorityError("paid provider hourly price must be positive")
        total_cap = min(
            float(decision.max_total_usd),
            self.runtime.hard_budget_policy.maximum_session_usd,
        )
        hourly_cap = min(
            float(decision.max_hourly_usd),
            float(model.max_hourly_usd),
            self.runtime.hard_budget_policy.maximum_hourly_usd,
        )
        if hourly_usd > hourly_cap:
            raise AuthorityError("provider hourly price exceeds the authoritative ceiling")
        approved_hours = min(float(maximum_session_hours), total_cap / hourly_usd)
        if approved_hours <= 0:
            raise AuthorityError("the approved budget permits no paid session")
        expires_at = (datetime.now(UTC) + timedelta(hours=approved_hours)).isoformat()
        lease = self.runtime.spend.issue_lease(
            decision_id=decision.id,
            subject="desktop-owner",
            expires_at=expires_at,
            backend=backend,
            model_id=model.id,
            maximum_hourly_usd=hourly_cap,
            maximum_total_usd=total_cap,
            maximum_attempts=1,
            fallback_allowed=False,
        )
        reservation_id = f"{record.execution_id}:{lease.lease_id}:primary"
        reservation = self.runtime.spend.reserve(
            lease,
            reservation_id=reservation_id,
            subject="desktop-owner",
            backend=backend,
            model_id=model.id,
            hourly_usd=hourly_usd,
            worst_case_usd=total_cap,
            metadata={
                "execution_id": record.execution_id,
                "provider": model.provider,
                "model_id": model.id,
            },
        )
        try:
            if record.state == ExecutionState.AWAITING_APPROVAL:
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.APPROVED,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                    detail={"lease_id": lease.lease_id},
                )
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.RESERVING,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                    detail={"reservation_id": reservation.reservation_id},
                )
                record = self.runtime.executions.bind_authority(
                    record.execution_id,
                    lease_id=lease.lease_id,
                    reservation_id=reservation.reservation_id,
                    hourly_usd=hourly_usd,
                    estimated_total_usd=total_cap,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                )
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.ACQUIRING,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.CREATING,
                    detail={"provider_mutation_authorized": True},
                )
            else:
                record = self.runtime.executions.bind_authority(
                    record.execution_id,
                    lease_id=lease.lease_id,
                    reservation_id=reservation.reservation_id,
                    hourly_usd=hourly_usd,
                    estimated_total_usd=total_cap,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                )
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.WARMING,
                    actor="mentat-v1-authority",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.WARMING,
                    detail={"existing_resource_reauthorized": True},
                )
        except Exception:
            with suppress(Exception):
                self.runtime.spend.release(
                    reservation.reservation_id,
                    reason="authority state transition failed before provider mutation",
                )
            raise
        return ProviderMutationGrant(
            decision_id=decision.id,
            execution_id=record.execution_id,
            model_id=model.id,
            backend=backend,
            hourly_usd=hourly_usd,
            worst_case_usd=total_cap,
            expires_at=expires_at,
            reservation_id=reservation.reservation_id,
            lease=lease,
        )

    def verify_provider_mutation(
        self,
        grant: ProviderMutationGrant | None,
        *,
        decision_id: str,
        model_id: str,
        hourly_usd: float,
    ) -> None:
        """Fail closed when the provider adapter is called without authority."""

        if grant is None:
            raise AuthorityError("Mentat 1.0 provider mutation grant is required")
        if grant.decision_id != decision_id or grant.model_id != model_id:
            raise AuthorityError("provider mutation grant does not match the decision")
        if hourly_usd > grant.hourly_usd + 1e-9:
            raise AuthorityError("provider mutation price exceeds its reserved price")
        grant.lease.verify(
            self.runtime.spend.signing_secret,
            subject="desktop-owner",
            backend=grant.backend,
            model_id=model_id,
        )
        reservation = self.runtime.spend.get(grant.reservation_id)
        if reservation is None or reservation.state not in {"reserved", "reconciling"}:
            raise AuthorityError("provider mutation has no active spend reservation")
        if reservation.lease_id != grant.lease.lease_id:
            raise AuthorityError("provider mutation reservation uses different authority")
        record = self.runtime.executions.get(grant.execution_id)
        if record is None:
            raise AuthorityError("provider mutation execution disappeared")
        if record.model_id != model_id or record.backend != grant.backend:
            raise AuthorityError("provider mutation execution does not match the model")
        if record.approval_lease_id != grant.lease.lease_id:
            raise AuthorityError("execution is not bound to the supplied lease")
        if record.spend_reservation_id != grant.reservation_id:
            raise AuthorityError("execution is not bound to the supplied reservation")
        if record.state not in {ExecutionState.ACQUIRING, ExecutionState.WARMING}:
            raise AuthorityError(
                f"provider mutation is not authorized from {record.state.value}"
            )

    def provider_acquired(
        self,
        grant: ProviderMutationGrant,
        resource: ProviderResource,
        *,
        ready: bool = False,
    ) -> ExecutionRecord:
        self.verify_provider_mutation(
            grant,
            decision_id=grant.decision_id,
            model_id=grant.model_id,
            hourly_usd=resource.hourly_usd,
        )
        record = self.runtime.executions.get(grant.execution_id)
        if record is None:
            raise AuthorityError("provider execution disappeared")
        if record.provider_resource_id:
            if record.provider_resource_id != resource.resource_id:
                raise AuthorityError("provider returned a different owned resource")
        else:
            record = self.runtime.executions.attach_resource(
                record.execution_id,
                resource,
                actor="vast-serverless-adapter",
                expected_version=record.version,
            )
        if record.state == ExecutionState.ACQUIRING:
            record = self.runtime.executions.transition(
                record.execution_id,
                ExecutionState.READY if ready else ExecutionState.WARMING,
                actor="vast-serverless-adapter",
                expected_version=record.version,
                provider_lifecycle=(
                    ProviderLifecycle.READY if ready else ProviderLifecycle.WARMING
                ),
                detail={"resource_id": resource.resource_id},
            )
        elif ready and record.state == ExecutionState.WARMING:
            record = self.runtime.executions.transition(
                record.execution_id,
                ExecutionState.READY,
                actor="vast-serverless-adapter",
                expected_version=record.version,
                provider_lifecycle=ProviderLifecycle.READY,
                detail={"resource_id": resource.resource_id},
            )
        return record

    def provider_ready(self, decision: Decision, model: ModelSpec) -> ExecutionRecord:
        record = self._execution_for_decision(decision)
        if record.model_id != model.id:
            raise AuthorityError("ready provider does not match the routed model")
        if record.state in {ExecutionState.ACQUIRING, ExecutionState.WARMING}:
            record = self.runtime.executions.transition(
                record.execution_id,
                ExecutionState.READY,
                actor="vast-serverless-adapter",
                expected_version=record.version,
                provider_lifecycle=ProviderLifecycle.READY,
                detail={"health_probe_passed": True},
            )
        if record.state != ExecutionState.READY:
            raise AuthorityError(f"provider is not ready: {record.state.value}")
        return record

    def assert_ready(self, model_id: str, decision: Decision | None = None) -> ExecutionRecord:
        if decision is not None:
            record = self._execution_for_decision(decision)
        else:
            record = self.active_execution_for_model(model_id)
            if record is None:
                raise AuthorityError("model has no authoritative execution")
        if record.model_id != model_id or record.state != ExecutionState.READY:
            raise AuthorityError("model route is not authorized and ready")
        if record.backend == BackendKind.VAST_SERVERLESS:
            if not record.spend_reservation_id:
                raise AuthorityError("paid route has no spend reservation")
            reservation = self.runtime.spend.get(record.spend_reservation_id)
            if reservation is None or reservation.state not in {"reserved", "reconciling"}:
                raise AuthorityError("paid route has no active spend authority")
        return record

    def reject(self, decision: Decision) -> None:
        record = self._execution_for_decision(decision)
        if record.state == ExecutionState.AWAITING_APPROVAL:
            self.runtime.executions.transition(
                record.execution_id,
                ExecutionState.REJECTED,
                actor="desktop-owner",
                expected_version=record.version,
                detail={"decision_id": decision.id},
            )

    def provider_failed(
        self,
        grant: ProviderMutationGrant,
        message: str,
        *,
        ambiguous: bool,
    ) -> None:
        record = self.runtime.executions.get(grant.execution_id)
        if record is None:
            return
        target = ExecutionState.AMBIGUOUS if ambiguous else ExecutionState.FAILED
        if record.state in {
            ExecutionState.ACQUIRING,
            ExecutionState.WARMING,
            ExecutionState.RESERVING,
        }:
            with suppress(Exception):
                self.runtime.executions.transition(
                    record.execution_id,
                    target,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=(
                        ProviderLifecycle.AMBIGUOUS
                        if ambiguous
                        else ProviderLifecycle.FAILED
                    ),
                    error_code="provider_mutation_failed",
                    error_message=message,
                    detail={"ambiguous_mutation": ambiguous},
                )
        if not ambiguous:
            with suppress(Exception):
                self.runtime.spend.release(
                    grant.reservation_id,
                    reason="provider mutation failed before remote state changed",
                )

    def no_spend_failed(self, decision: Decision, message: str) -> None:
        record = self._execution_for_decision(decision)
        if record.state in {
            ExecutionState.APPROVED,
            ExecutionState.RESERVING,
            ExecutionState.ACQUIRING,
            ExecutionState.WARMING,
        }:
            with suppress(Exception):
                self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.FAILED,
                    actor="external-provider-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.FAILED,
                    error_code="external_provider_failed",
                    error_message=message,
                )

    def provider_cooled(self, model_id: str, *, reason: str) -> None:
        record = self.active_execution_for_model(model_id)
        if record is None or record.state == ExecutionState.COOLED:
            return
        try:
            if record.state == ExecutionState.ACQUIRING:
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.AMBIGUOUS,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.AMBIGUOUS,
                    detail={"reason": reason},
                )
            if record.state in {ExecutionState.AMBIGUOUS, ExecutionState.FAILED}:
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.RECONCILING,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    detail={"reason": reason},
                )
            if record.state in {
                ExecutionState.WARMING,
                ExecutionState.READY,
                ExecutionState.RECONCILING,
            }:
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.COOLING,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.COOLING,
                    detail={"reason": reason},
                )
            if record.state == ExecutionState.COOLING:
                self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.COOLED,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.COOLED,
                    detail={
                        "reason": reason,
                        "billing_reconciliation_required": bool(
                            record.spend_reservation_id
                        ),
                    },
                )
        except Exception as exc:
            self.provider_cool_failed(model_id, message=str(exc))

    def provider_cool_failed(self, model_id: str, *, message: str) -> None:
        record = self.active_execution_for_model(model_id)
        if record is None or record.state == ExecutionState.AMBIGUOUS:
            return
        try:
            if record.state in {ExecutionState.WARMING, ExecutionState.READY}:
                record = self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.COOLING,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.COOLING,
                )
            if record.state == ExecutionState.COOLING:
                self.runtime.executions.transition(
                    record.execution_id,
                    ExecutionState.AMBIGUOUS,
                    actor="vast-serverless-adapter",
                    expected_version=record.version,
                    provider_lifecycle=ProviderLifecycle.AMBIGUOUS,
                    error_code="provider_cool_failed",
                    error_message=message,
                )
        except Exception:
            return

    def reconcile_sessions(self, sessions: list[dict[str, Any]]) -> None:
        """Bring the authoritative ledger in line with startup cooling results."""

        for session in sessions:
            model_id = str(session.get("model_id") or "")
            if not model_id:
                continue
            if session.get("status") == "cooled":
                self.provider_cooled(model_id, reason="startup reconciliation")
            elif session.get("status") == "failed":
                self.provider_cool_failed(
                    model_id,
                    message=str(session.get("error") or "startup reconciliation failed"),
                )

    def active_execution_for_model(
        self,
        model_id: str,
        *,
        include_cooled: bool = False,
    ) -> ExecutionRecord | None:
        allowed = set(self.ACTIVE_STATES)
        if include_cooled:
            allowed.add(ExecutionState.COOLED)
        for record in self.runtime.executions.list(limit=500):
            if record.model_id == model_id and record.state in allowed:
                return record
        return None

    def _execution_for_decision(self, decision: Decision) -> ExecutionRecord:
        raw = decision.metadata.get("authority_execution_id")
        execution_id = str(raw or decision.id)
        record = self.runtime.executions.get(execution_id)
        if record is None:
            raise AuthorityError("decision has no Mentat 1.0 authority record")
        return record

    @staticmethod
    def _bind_decision_metadata(
        decision: Decision,
        record: ExecutionRecord,
        *,
        reused: bool,
    ) -> None:
        decision.metadata["authority_owner"] = "mentat-v1"
        decision.metadata["authority_execution_id"] = record.execution_id
        decision.metadata["authority_reused_execution"] = reused
        decision.metadata["candidate_generator"] = "legacy-production-router"

    def _validate_route(self, decision: Decision, model: ModelSpec) -> None:
        if decision.selected_model != model.id or decision.selected_model_id != model.model_id:
            raise AuthorityError("selected route does not match the model registry")
        if not model.enabled:
            raise AuthorityError("selected model is disabled")
        hard = self.runtime.hard_budget_policy
        if decision.max_hourly_usd > hard.maximum_hourly_usd:
            raise AuthorityError("route exceeds the immutable hourly policy")
        if decision.max_total_usd > hard.maximum_session_usd:
            raise AuthorityError("route exceeds the immutable session policy")
        if decision.estimated_cost_usd > decision.max_total_usd + 1e-9:
            raise AuthorityError("route estimate exceeds its approved total ceiling")
        if decision.offer and decision.offer.hourly_usd > decision.max_hourly_usd + 1e-9:
            raise AuthorityError("route offer exceeds its approved hourly ceiling")
        requirements = dict(decision.metadata.get("requirements") or {})
        task_class = str(requirements.get("task_class") or decision.task_class)
        if task_class not in model.task_classes:
            raise AuthorityError("selected model does not support the routed task class")
        capabilities = {str(value) for value in requirements.get("capabilities", [])}
        if not capabilities.issubset(model.capabilities):
            raise AuthorityError("selected model is missing required capabilities")
        estimated_tokens = int(requirements.get("estimated_input_tokens") or 0)
        if estimated_tokens > model.context_tokens:
            raise AuthorityError("selected model context is smaller than the request")
