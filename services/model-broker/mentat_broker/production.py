from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from . import server as broker_server
from .authority import BrokerAuthority, ProviderMutationGrant
from .contracts import ProviderLifecycle, ProviderResource, utc_now
from .endpoint_overrides import install_endpoint_override_hooks
from .model_controls import SettingsAwareRegistry
from .models import Decision, ModelSpec
from .production_app import ProductionBrokerApplication
from .production_http import (
    LoopbackThreadingHTTPServer,
    production_read_json,
    set_max_body_bytes,
)
from .production_sessions import ProductionSessionManager
from .production_store import ProductionBrokerStore
from .runtime import MentatV1Runtime
from .sessions import SessionError
from .spend import BudgetPolicy
from .v1_http import v1_handler_factory


class AuthoritativeProductionSessionManager(ProductionSessionManager):
    """Vast adapter that refuses paid mutations without a Mentat grant."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._authority: BrokerAuthority | None = None
        self._authority_stop = threading.Event()
        self._authority_thread: threading.Thread | None = None

    def set_authority(self, authority: BrokerAuthority) -> None:
        self._authority = authority
        if self._authority_thread and self._authority_thread.is_alive():
            return
        self._authority_stop.clear()
        self._authority_thread = threading.Thread(
            target=self._authority_reconcile_loop,
            name="mentat-authority-reconcile",
            daemon=True,
        )
        self._authority_thread.start()

    def approve(
        self,
        decision: Decision,
        *,
        accept_benchmark_cost: bool,
        authority_grant: ProviderMutationGrant | None = None,
    ) -> Decision:
        model = self.registry.get(decision.selected_model)
        if model.provider == "vast":
            if self._authority is None:
                raise RuntimeError("Mentat 1.0 authority is not installed")
            hourly_usd = (
                decision.offer.hourly_usd
                if decision.offer
                else min(model.max_hourly_usd, decision.max_hourly_usd)
            )
            self._authority.verify_provider_mutation(
                authority_grant,
                decision_id=decision.id,
                model_id=model.id,
                hourly_usd=hourly_usd,
            )
        updated = super().approve(
            decision,
            accept_benchmark_cost=accept_benchmark_cost,
        )
        if authority_grant is not None:
            session = self.store.get_session(model.id) or {}
            self.store.upsert_session(
                model.id,
                status=str(session.get("status") or "approved"),
                endpoint_url=session.get("endpoint_url"),
                hourly_usd=session.get("hourly_usd"),
                decision_id=decision.id,
                last_used_at=session.get("last_used_at"),
                approved_until=authority_grant.expires_at,
            )
        return updated

    def stop_sweeper(self) -> None:
        self._authority_stop.set()
        if self._authority_thread:
            self._authority_thread.join(timeout=3)
        super().stop_sweeper()

    def reconcile_startup(self) -> None:
        super().reconcile_startup()
        self._reconcile_authority_once()

    def cool_all(self, timeout_seconds: int) -> None:
        super().cool_all(timeout_seconds)
        self._reconcile_authority_once()

    def cool_now(self, model_id: str) -> dict[str, Any]:
        """Perform the provider action, then report it to the authority ledger."""

        with self._approval_lock:
            session = self.store.get_session(model_id)
            if session is None:
                raise KeyError("saved compute session not found")
            model = self.registry.get(model_id)
            try:
                if model.provider == "vast":
                    self._lifecycle(model, "cool")
                self.store.upsert_session(model.id, status="cooled", error=None)
                if self._authority is not None:
                    self._authority.provider_cooled(
                        model.id,
                        reason="manual Control Center request",
                    )
            except Exception as exc:
                self.store.upsert_session(model.id, status="failed", error=str(exc))
                if self._authority is not None:
                    self._authority.provider_cool_failed(model.id, message=str(exc))
                raise
            updated = self.store.get_session(model.id)
            if updated is None:
                raise SessionError("saved compute session disappeared after cooling")
            return updated

    def _authority_reconcile_loop(self) -> None:
        while not self._authority_stop.wait(5):
            self._reconcile_authority_once()

    def _reconcile_authority_once(self) -> None:
        if self._authority is None:
            return
        self._authority.reconcile_sessions(self.store.list_sessions())


class MentatV1ProductionApplication(ProductionBrokerApplication):
    """Production adapters governed by one Mentat 1.0 authority."""

    def __init__(self, root: Path, registry_path: Path, data_dir: Path):
        super().__init__(root, registry_path, data_dir)
        policy = self.registry.policy
        try:
            self.v1 = MentatV1Runtime(
                data_dir / "mentat-v1",
                budget_policy=BudgetPolicy(
                    maximum_hourly_usd=policy.max_hourly_usd,
                    maximum_session_usd=policy.max_total_usd,
                    maximum_daily_usd=max(policy.max_total_usd, policy.max_total_usd * 2),
                    maximum_monthly_usd=max(policy.max_total_usd, policy.max_total_usd * 20),
                    maximum_retry_usd=max(0.01, policy.max_total_usd * 0.15),
                    maximum_fallback_usd=max(0.01, policy.max_total_usd * 0.30),
                    maximum_exploration_usd=max(0.01, policy.max_total_usd * 0.05),
                    one_paid_session=True,
                ),
            )
            lifecycle_registry = self.registry
            self.registry = SettingsAwareRegistry(lifecycle_registry, self.v1.settings)
            self.authority = BrokerAuthority(self.v1)
            self.sessions.set_authority(self.authority)
            self.authority.reconcile_sessions(self.store.list_sessions())
        except Exception:
            super().close()
            raise

    def plan(self, payload: dict[str, Any]) -> Decision:
        """Treat the established router as a candidate generator, never authority."""

        settings = self.v1.settings.load()
        effective_payload = dict(payload)
        requested_hourly = effective_payload.get("max_hourly_usd")
        requested_total = effective_payload.get("max_total_usd")
        effective_payload["max_hourly_usd"] = min(
            float(requested_hourly)
            if requested_hourly is not None
            else settings.budgets.maximum_hourly_usd,
            settings.budgets.maximum_hourly_usd,
        )
        effective_payload["max_total_usd"] = min(
            float(requested_total)
            if requested_total is not None
            else settings.budgets.maximum_session_usd,
            settings.budgets.maximum_session_usd,
        )
        decision = super().plan(effective_payload)
        model = self.registry.get(decision.selected_model)
        try:
            self.authority.register_decision(decision, model)
        except Exception as exc:
            self.store.update_decision_status(
                decision.id,
                "failed",
                error=f"Mentat 1.0 authority rejected route: {exc}",
                completed_at=utc_now(),
            )
            self.coordinator.notify()
            raise
        decision.reasons.append(
            "Mentat 1.0 accepted this route as the single spend and execution authority."
        )
        self.store.save_decision(decision)
        return decision

    def approve(self, decision_id: str, payload: dict[str, Any]) -> Decision:
        decision = self.store.get_decision(decision_id)
        if not decision:
            raise KeyError("decision not found")
        if decision.status != "pending":
            return decision
        model = self.registry.get(decision.selected_model)
        accept_benchmark_cost = bool(payload.get("accept_benchmark_cost", False))
        if (
            model.provider == "vast"
            and bool(decision.metadata.get("requires_endpoint_creation"))
            and not accept_benchmark_cost
        ):
            raise SessionError(
                "Creating a new Vast endpoint requires explicit benchmark-cost acknowledgement"
            )

        if model.provider == "external":
            self.authority.prepare_no_spend_provider(decision, model)
            try:
                updated = self.sessions.approve(
                    decision,
                    accept_benchmark_cost=accept_benchmark_cost,
                )
                self.authority.provider_ready(updated, model)
                return updated
            except Exception as exc:
                self.authority.no_spend_failed(decision, str(exc))
                raise

        settings = self.v1.settings.load()
        if settings.privacy_mode != "remote_allowed":
            raise SessionError("desktop privacy mode blocks remote inference")
        if not settings.remote_inference_enabled:
            raise SessionError("remote inference is disabled in desktop settings")
        exposure = self.v1.spend.snapshot()
        if (
            float(exposure["today_exposure_usd"]) + decision.max_total_usd
            > settings.budgets.maximum_daily_usd
        ):
            raise SessionError("desktop daily spend ceiling would be exceeded")
        if (
            float(exposure["month_exposure_usd"]) + decision.max_total_usd
            > settings.budgets.maximum_monthly_usd
        ):
            raise SessionError("desktop monthly spend ceiling would be exceeded")
        hourly_usd = (
            decision.offer.hourly_usd
            if decision.offer
            else min(model.max_hourly_usd, decision.max_hourly_usd)
        )
        grant = self.authority.prepare_paid_provider(
            decision,
            model,
            hourly_usd=hourly_usd,
            maximum_session_hours=self.registry.policy.max_session_hours,
        )
        try:
            updated = self.sessions.approve(
                decision,
                accept_benchmark_cost=accept_benchmark_cost,
                authority_grant=grant,
            )
            resource = self._provider_resource(updated, model, hourly_usd)
            self.authority.provider_acquired(grant, resource, ready=False)
            return updated
        except Exception as exc:
            self.authority.provider_failed(grant, str(exc), ambiguous=True)
            raise

    def reject(self, decision_id: str) -> Decision:
        decision = self.store.get_decision(decision_id)
        if not decision:
            raise KeyError("decision not found")
        self.authority.reject(decision)
        rejected = super().reject(decision_id)
        return rejected

    def prepare_chat(self, payload: dict[str, Any]):
        decision, model, endpoint = super().prepare_chat(payload)
        self.authority.provider_ready(decision, model)
        self.authority.assert_ready(model.id, decision)
        return decision, model, endpoint

    def _proxy_to_model(
        self,
        handler: Any,
        payload: dict[str, Any],
        model: ModelSpec,
        base_url: str,
        decision: Decision,
        started: float,
    ) -> None:
        authoritative_decision = decision if model.id == decision.selected_model else None
        self.authority.assert_ready(model.id, authoritative_decision)
        super()._proxy_to_model(
            handler,
            payload,
            model,
            base_url,
            decision,
            started,
        )

    def _provider_resource(
        self,
        decision: Decision,
        model: ModelSpec,
        hourly_usd: float,
    ) -> ProviderResource:
        endpoint_url = self.sessions.endpoint_url(model)
        state: dict[str, Any] = {}
        try:
            state = json.loads(self.sessions.endpoint_state_path(model).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, SessionError):
            state = {}
        endpoint_id = state.get("endpoint_id")
        workergroup_id = state.get("workergroup_id")
        if endpoint_id is None or workergroup_id is None:
            raise SessionError(
                "Vast mutation completed without durable endpoint and workergroup identity; "
                "manual reconciliation is required"
            )
        resource_id = f"vast-serverless:{endpoint_id}:{workergroup_id}"
        return ProviderResource(
            backend=self.authority.backend_for(model),
            resource_id=resource_id,
            lifecycle=ProviderLifecycle.WARMING,
            model_id=model.id,
            hourly_usd=float(hourly_usd),
            created_at=str(state.get("created_at") or utc_now()),
            last_observed_at=utc_now(),
            endpoint_url=endpoint_url,
            metadata={
                "endpoint_id": endpoint_id,
                "workergroup_id": workergroup_id,
                "identity_source": "vast-state",
                "decision_id": decision.id,
            },
        )

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.v1.close()


def install_production_hooks() -> None:
    """Install the final production gates after safety and runtime hooks."""

    install_endpoint_override_hooks()
    base_make_handler = broker_server.make_handler
    base_ui = broker_server._decision_ui

    def make_handler(application: MentatV1ProductionApplication):
        set_max_body_bytes(application.registry.policy.max_request_body_bytes)
        return v1_handler_factory(base_make_handler, base_ui, application)

    broker_server.BrokerStore = ProductionBrokerStore
    broker_server.EndpointSessionManager = AuthoritativeProductionSessionManager
    broker_server.BrokerApplication = MentatV1ProductionApplication
    broker_server.ThreadingHTTPServer = LoopbackThreadingHTTPServer
    broker_server._read_json = production_read_json
    broker_server.make_handler = make_handler
