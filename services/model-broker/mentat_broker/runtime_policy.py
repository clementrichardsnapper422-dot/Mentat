from __future__ import annotations

import threading
from typing import Any

from . import server as broker_server
from .models import Decision
from .safety import SafeBrokerApplication, SafeEndpointSessionManager
from .sessions import SessionError
from .store import BrokerStore, utc_now


class QualityAwareBrokerStore(BrokerStore):
    """Separate rated quality samples from automatic runtime measurements."""

    def benchmark_summary(self, model_id: str, task_class: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    COUNT(*) AS runtime_samples,
                    COUNT(quality_score) AS quality_samples,
                    AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) AS success_rate,
                    AVG(latency_ms) AS latency_ms,
                    AVG(tokens_per_second) AS tokens_per_second,
                    AVG(hourly_usd) AS hourly_usd,
                    AVG(total_cost_usd) AS total_cost_usd,
                    AVG(quality_score) AS quality_score
                FROM benchmarks
                WHERE model_id = ? AND task_class = ?
                """,
                (model_id, task_class),
            ).fetchone()
        return {
            "samples": int(row["quality_samples"] or 0),
            "runtime_samples": int(row["runtime_samples"] or 0),
            "success_rate": float(row["success_rate"] or 0),
            "latency_ms": float(row["latency_ms"]) if row["latency_ms"] is not None else None,
            "tokens_per_second": (
                float(row["tokens_per_second"]) if row["tokens_per_second"] is not None else None
            ),
            "hourly_usd": (float(row["hourly_usd"]) if row["hourly_usd"] is not None else None),
            "total_cost_usd": (
                float(row["total_cost_usd"]) if row["total_cost_usd"] is not None else None
            ),
            "quality_score": (
                float(row["quality_score"]) if row["quality_score"] is not None else None
            ),
        }


class SerializedEndpointSessionManager(SafeEndpointSessionManager):
    """Serialize approvals so two clicks cannot start overlapping paid clusters."""

    _approval_lock = threading.RLock()

    def approve(self, decision: Decision, *, accept_benchmark_cost: bool) -> Decision:
        with self._approval_lock:
            return super().approve(
                decision,
                accept_benchmark_cost=accept_benchmark_cost,
            )


class ContextAwareBrokerApplication(SafeBrokerApplication):
    """Route on the latest user intent while sizing the entire model context."""

    def prepare_chat(self, payload: dict[str, Any]):
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be an array")
        prompt, has_images = self.routing_prompt_from_messages(messages)
        full_context, _ = self._prompt_from_messages(messages)
        explicit_tools = payload.get("mentat_requires_tools")
        requires_tools = (
            bool(explicit_tools)
            if explicit_tools is not None
            else self.task_requires_tools(prompt, bool(payload.get("tools")))
        )
        decision = self.plan(
            {
                "prompt": prompt,
                "has_images": has_images,
                "requires_tools": requires_tools,
                "estimated_input_tokens": max(1, len(full_context) // 4),
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
        endpoint = self.sessions.wait_until_ready(model)
        return decision, model, endpoint


def install_runtime_policy_hooks() -> None:
    """Install final concurrency, quality, and context policies."""

    broker_server.BrokerStore = QualityAwareBrokerStore
    broker_server.EndpointSessionManager = SerializedEndpointSessionManager
    broker_server.BrokerApplication = ContextAwareBrokerApplication
