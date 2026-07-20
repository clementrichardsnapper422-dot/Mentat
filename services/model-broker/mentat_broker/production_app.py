from __future__ import annotations

import json
import math
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler
from typing import Any

from .models import Decision, ModelSpec, Offer
from .production_sessions import ProductionSessionManager
from .production_store import ProductionBrokerStore
from .registry import ModelRegistry
from .router import RoutingError, build_decision, classify_task
from .runtime_policy import ContextAwareBrokerApplication
from .sessions import ApprovalCoordinator, SessionError
from .store import utc_now


class RegistryView:
    def __init__(self, registry: ModelRegistry, models: list[ModelSpec]):
        self._registry = registry
        self._models = models
        self.policy = registry.policy

    def enabled(self) -> list[ModelSpec]:
        return list(self._models)

    def get(self, model_id: str) -> ModelSpec:
        return self._registry.get(model_id)


class ProductionBrokerApplication(ContextAwareBrokerApplication):
    """Production routing, authentication state, and graceful endpoint shutdown."""

    FOLLOWUP_TERMS = {
        "go",
        "do it",
        "yes",
        "continue",
        "proceed",
        "make it so",
        "fix it",
        "ship it",
        "merge it",
    }

    def __init__(self, *args: Any, **kwargs: Any):
        check_mode = "--check" in sys.argv
        self.client_token = os.getenv("MENTAT_BROKER_CLIENT_TOKEN") or (
            "check-client" if check_mode else ""
        )
        self.admin_token = os.getenv("MENTAT_BROKER_ADMIN_TOKEN") or (
            "check-admin" if check_mode else ""
        )
        if not self.client_token or not self.admin_token:
            raise RuntimeError("broker client and admin tokens are required")
        super().__init__(*args, **kwargs)
        self._ensure_production_dependencies()
        if (
            not check_mode
            and any(model.provider == "vast" for model in self.registry.enabled())
            and not os.getenv("VAST_API_KEY")
        ):
            self.store.close()
            raise RuntimeError("VAST_API_KEY must be available only to the broker process")
        self.request_slots = threading.BoundedSemaphore(
            self.registry.policy.max_concurrent_requests
        )
        if not check_mode:
            self.sessions.stop_sweeper()
            self.sessions.reconcile_startup()
            self.sessions.start_sweeper()

    def _ensure_production_dependencies(self) -> None:
        """Remove startup-order dependence from the production application.

        The command-line entry point installs compatibility hooks before creating
        the application. Tests, embedders, and future entry points may construct
        this class directly. In every case, production code must use the durable
        store and fail-safe endpoint manager rather than whichever globals were
        active when the base class was initialized.
        """

        if isinstance(self.store, ProductionBrokerStore) and isinstance(
            self.sessions, ProductionSessionManager
        ):
            return
        self.sessions.stop_sweeper()
        self.store.close()
        self.store = ProductionBrokerStore(self.data_dir / "broker.sqlite3")
        self.coordinator = ApprovalCoordinator()
        self.sessions = ProductionSessionManager(
            root=self.root,
            state_dir=self.data_dir / "endpoints",
            registry=self.registry,
            store=self.store,
            coordinator=self.coordinator,
        )

    def routing_prompt_from_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str, bool]:
        user_messages = [
            message for message in messages if str(message.get("role") or "") == "user"
        ]
        if not user_messages:
            return self._prompt_from_messages(messages[-1:])
        latest, has_images = self._prompt_from_messages(user_messages[-1:])
        normalized = " ".join(latest.lower().split())
        if len(user_messages) > 1 and (
            normalized in self.FOLLOWUP_TERMS or len(normalized) < 8
        ):
            previous, previous_images = self._prompt_from_messages(user_messages[-2:-1])
            return f"{previous}\nFollow-up: {latest}".strip(), has_images or previous_images
        return latest, has_images

    def _eligible_models(self, task_class: str) -> list[ModelSpec]:
        allow_unmeasured = os.getenv("MENTAT_ALLOW_UNMEASURED_MODELS") == "1"
        result: list[ModelSpec] = []
        for model in self.registry.enabled():
            if model.id == self.registry.policy.primary_model_id:
                result.append(model)
                continue
            if allow_unmeasured or not self.registry.policy.require_measured_quality_for_non_primary:
                result.append(model)
                continue
            summary = self.store.benchmark_summary(model.id, task_class)
            if (
                int(summary.get("samples") or 0) >= model.minimum_benchmark_samples
                and summary.get("quality_score") is not None
            ):
                result.append(model)
        return result

    def _session_offer(self, model: ModelSpec) -> Offer | None:
        session = self.store.get_session(model.id)
        if not session or not self.sessions.is_approved(model.id):
            return None
        raw = session.get("offer")
        if isinstance(raw, dict):
            try:
                return Offer(**raw)
            except (TypeError, ValueError):
                pass
        return Offer(
            id=-1,
            gpu_name=model.gpu_names[0] if model.gpu_names else "approved endpoint",
            num_gpus=model.num_gpus,
            gpu_ram_mb=model.min_gpu_ram_mb,
            hourly_usd=float(session.get("hourly_usd") or model.max_hourly_usd),
            reliability=1.0,
            verified=True,
            disk_space_gb=float(model.min_disk_gb),
        )

    def plan(self, payload: dict[str, Any]) -> Decision:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        requirements = classify_task(
            prompt,
            estimated_input_tokens=int(payload.get("estimated_input_tokens") or 0),
            has_images=bool(payload.get("has_images", False)),
            requires_tools=bool(payload.get("requires_tools", True)),
            risk_level=str(payload.get("risk_level") or "normal"),
        )
        if self.registry.policy.serverless_text_only and requirements.task_class == "vision":
            raise RoutingError(
                "the configured Vast Serverless route is text-only; add a validated vision provider"
            )

        eligible = self._eligible_models(requirements.task_class)
        offers: dict[str, list[Offer]] = {}
        for model in eligible:
            if requirements.task_class not in model.task_classes or model.provider != "vast":
                continue
            reusable = self._session_offer(model)
            offers[model.id] = [reusable] if reusable else self.offers_for(model)

        decision = build_decision(
            prompt=prompt,
            registry=RegistryView(self.registry, eligible),  # type: ignore[arg-type]
            store=self.store,
            offers_by_model=offers,
            estimated_input_tokens=int(payload.get("estimated_input_tokens") or 0),
            has_images=bool(payload.get("has_images", False)),
            requires_tools=bool(payload.get("requires_tools", True)),
            risk_level=str(payload.get("risk_level") or "normal"),
            max_hourly_usd=(
                float(payload["max_hourly_usd"])
                if payload.get("max_hourly_usd") is not None
                else None
            ),
            max_total_usd=(
                float(payload["max_total_usd"])
                if payload.get("max_total_usd") is not None
                else None
            ),
        )
        selected = self.registry.get(decision.selected_model)
        if (
            selected.provider == "vast"
            and self.registry.policy.require_live_offer
            and decision.offer is None
        ):
            raise RoutingError(
                f"no live Vast offer satisfies the production requirements for {selected.display_name}"
            )
        decision.metadata["requires_endpoint_creation"] = (
            selected.provider == "vast"
            and not self.sessions.endpoint_state_path(selected).exists()
        )
        decision.metadata["approved_price_ceiling_usd"] = (
            decision.offer.hourly_usd if decision.offer else selected.max_hourly_usd
        )
        if decision.metadata["requires_endpoint_creation"]:
            decision.reasons.append(
                "No saved endpoint exists for this model; approval may run Vast's initial benchmark worker."
            )
        if self.sessions.is_approved(selected.id):
            decision.status = "approved"
            decision.reasons.append(
                "Reusing an approved active session; no new paid launch is requested."
            )
        elif (
            selected.id == self.registry.policy.primary_model_id
            and self.registry.policy.require_measured_quality_for_non_primary
        ):
            decision.reasons.append(
                "Production policy keeps Kimi primary until cheaper models have enough rated local evidence."
            )
        self.store.save_decision(decision)
        return decision

    def prepare_chat(self, payload: dict[str, Any]):
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty array")
        prompt, routing_images = self.routing_prompt_from_messages(messages)
        _full_text, full_images = self._prompt_from_messages(messages)
        if self.registry.policy.serverless_text_only and (routing_images or full_images):
            raise RoutingError(
                "image input is not supported by the configured Vast Serverless proxy"
            )
        tools = payload.get("tools")
        explicit_tools = payload.get("mentat_requires_tools")
        requires_tools = (
            bool(explicit_tools)
            if explicit_tools is not None
            else self.task_requires_tools(prompt, bool(tools))
        )
        serialized = json.dumps(
            {"messages": messages, "tools": tools or []},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        requested_output = int(payload.get("max_tokens") or 16384)
        estimated_tokens = math.ceil(len(serialized) / 3.5 * 1.15) + requested_output
        decision = self.plan(
            {
                "prompt": prompt,
                "has_images": False,
                "requires_tools": requires_tools,
                "estimated_input_tokens": estimated_tokens,
                "risk_level": payload.get("mentat_risk_level", "normal"),
                "max_hourly_usd": payload.get("mentat_max_hourly_usd"),
                "max_total_usd": payload.get("mentat_max_total_usd"),
            }
        )
        model = self.registry.get(decision.selected_model)
        if decision.status == "pending":
            resolved = self.coordinator.wait_for_terminal(
                self.store,
                decision.id,
                self.registry.policy.approval_timeout_seconds,
            )
            if not resolved or resolved.status in {"pending", "warming"}:
                self.store.update_decision_status(
                    decision.id,
                    "timed_out",
                    error="approval timed out",
                    completed_at=utc_now(),
                )
                raise SessionError(f"compute approval timed out for decision {decision.id}")
            if resolved.status == "rejected":
                raise PermissionError(f"compute decision {decision.id} was rejected")
            if resolved.status == "failed":
                raise SessionError(resolved.error or "endpoint approval failed")
            decision = resolved
        self.sessions.set_current_decision(decision)
        endpoint = self.sessions.wait_until_ready(model)
        return decision, model, endpoint

    def proxy_chat(self, handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
        try:
            super().proxy_chat(handler, payload)
        finally:
            self.sessions.set_current_decision(None)

    def _proxy_to_model(
        self,
        handler: BaseHTTPRequestHandler,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        original = handler.send_response

        def tracked(code: int, message: str | None = None) -> None:
            if 200 <= int(code) < 400:
                handler._mentat_upstream_started = True  # type: ignore[attr-defined]
            original(code, message)

        handler.send_response = tracked  # type: ignore[method-assign]
        try:
            super()._proxy_to_model(handler, *args, **kwargs)
        finally:
            handler.send_response = original  # type: ignore[method-assign]

    def _json_error(
        self,
        handler: BaseHTTPRequestHandler,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if getattr(handler, "_mentat_upstream_started", False):
            handler.close_connection = True
            return
        super()._json_error(handler, *args, **kwargs)

    def close(self) -> None:
        self.sessions.stop_sweeper()
        try:
            self.sessions.cool_all(self.registry.policy.shutdown_cooldown_timeout_seconds)
        finally:
            self.store.close()
