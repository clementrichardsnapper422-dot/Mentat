from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from .models import Decision, ModelSpec
from .runtime_policy import SerializedEndpointSessionManager


class ProductionSessionManager(SerializedEndpointSessionManager):
    """Fail-safe endpoint lifecycle, capability-aware fallbacks, and crash recovery."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._thread_state = threading.local()

    def start_sweeper(self) -> None:
        self._stop_event.clear()
        super().start_sweeper()

    def set_current_decision(self, decision: Decision | None) -> None:
        self._thread_state.decision = decision

    def _probe(self, base_url: str) -> bool:
        model = getattr(self._thread_state, "probe_model", None)
        if not isinstance(model, ModelSpec):
            return False
        api_key = os.getenv("VAST_API_KEY") or "EMPTY"
        payload = json.dumps(
            {
                "model": model.model_id,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "MentatBroker/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                response.read(4096)
                return 200 <= response.status < 300
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return False

    def wait_until_ready(self, model: ModelSpec, timeout_seconds: int | None = None) -> str:
        self._thread_state.probe_model = model
        try:
            return super().wait_until_ready(model, timeout_seconds)
        finally:
            self._thread_state.probe_model = None

    def _fallback_satisfies(self, fallback: ModelSpec, decision: Decision) -> bool:
        requirements = dict(decision.metadata.get("requirements") or {})
        task_class = str(requirements.get("task_class") or decision.task_class)
        capabilities = {str(item) for item in requirements.get("capabilities", [])}
        minimum_tier = int(requirements.get("minimum_quality_tier") or 1)
        input_tokens = int(requirements.get("estimated_input_tokens") or 0)
        if not fallback.enabled or task_class not in fallback.task_classes:
            return False
        if fallback.quality_tier < minimum_tier:
            return False
        if not capabilities.issubset(fallback.capabilities):
            return False
        if input_tokens and fallback.context_tokens < input_tokens:
            return False
        if (
            self.registry.policy.require_measured_quality_for_non_primary
            and fallback.id != self.registry.policy.primary_model_id
        ):
            summary = self.store.benchmark_summary(fallback.id, task_class)
            if int(summary.get("samples") or 0) < fallback.minimum_benchmark_samples:
                return False
            if summary.get("quality_score") is None:
                return False
        return True

    def ready_fallbacks(self, model: ModelSpec) -> list[ModelSpec]:
        decision = getattr(self._thread_state, "decision", None)
        if not isinstance(decision, Decision):
            return []
        result: list[ModelSpec] = []
        for fallback_id in model.fallback_chain:
            if not self.is_approved(fallback_id):
                continue
            fallback = self.registry.get(fallback_id)
            if self._fallback_satisfies(fallback, decision):
                result.append(fallback)
        return result

    def approve(self, decision: Decision, *, accept_benchmark_cost: bool) -> Decision:
        temporary = self.state_dir / f"approved-{decision.selected_model}-{decision.id}.json"
        try:
            return super().approve(
                decision,
                accept_benchmark_cost=accept_benchmark_cost,
            )
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def reconcile_startup(self) -> None:
        """Cool saved Vast endpoints after an unclean broker exit.

        A restarted broker never assumes an old local approval remains valid.
        """

        for model in self.registry.enabled():
            if model.provider != "vast" or not self.endpoint_state_path(model).exists():
                continue
            try:
                self._lifecycle(model, "cool")
                self.store.upsert_session(model.id, status="cooled")
            except Exception as exc:
                self.store.upsert_session(model.id, status="failed", error=str(exc))

    def cool_all(self, timeout_seconds: int) -> None:
        threads: list[threading.Thread] = []

        def cool(model: ModelSpec) -> None:
            try:
                self._lifecycle(model, "cool")
                self.store.upsert_session(model.id, status="cooled")
            except Exception as exc:
                self.store.upsert_session(model.id, status="failed", error=str(exc))

        for model in self.registry.enabled():
            if model.provider == "vast" and self.endpoint_state_path(model).exists():
                thread = threading.Thread(target=cool, args=(model,), daemon=True)
                thread.start()
                threads.append(thread)
        deadline = time.monotonic() + max(1, timeout_seconds)
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(30):
            now = datetime.now(UTC)
            for session in self.store.list_sessions():
                if session["status"] not in {"approved", "warming", "ready"}:
                    continue
                model = self.registry.get(str(session["model_id"]))
                if model.provider != "vast":
                    continue
                last_raw = session.get("last_used_at") or session.get("started_at")
                try:
                    last_used = datetime.fromisoformat(str(last_raw))
                except (TypeError, ValueError):
                    last_used = now
                idle_minutes = (now - last_used).total_seconds() / 60
                expired = not self._session_not_expired(session, now)
                warming_stale = (
                    session["status"] == "warming"
                    and (now - last_used).total_seconds()
                    > self.registry.policy.endpoint_ready_timeout_seconds
                )
                if (
                    not expired
                    and not warming_stale
                    and idle_minutes < self.registry.policy.idle_shutdown_minutes
                ):
                    continue
                try:
                    self._lifecycle(model, "cool")
                    self.store.upsert_session(model.id, status="cooled")
                except Exception as exc:
                    self.store.upsert_session(model.id, status="failed", error=str(exc))
