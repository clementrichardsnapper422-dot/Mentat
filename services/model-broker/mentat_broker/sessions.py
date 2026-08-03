from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Decision, ModelSpec
from .registry import ModelRegistry
from .store import BrokerStore, utc_now


class SessionError(RuntimeError):
    """Raised when an endpoint session cannot be started or reused."""


class ApprovalCoordinator:
    def __init__(self):
        self._condition = threading.Condition()

    def notify(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def wait_for_terminal(
        self,
        store: BrokerStore,
        decision_id: str,
        timeout_seconds: int,
    ) -> Decision | None:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while time.monotonic() < deadline:
                decision = store.get_decision(decision_id)
                if decision and decision.status not in {"pending", "warming"}:
                    return decision
                remaining = deadline - time.monotonic()
                self._condition.wait(timeout=min(1.0, max(0.0, remaining)))
        return store.get_decision(decision_id)


class EndpointSessionManager:
    def __init__(
        self,
        *,
        root: Path,
        state_dir: Path,
        registry: ModelRegistry,
        store: BrokerStore,
        coordinator: ApprovalCoordinator,
        on_pending: Callable[[Decision], None] | None = None,
    ):
        self.root = root
        self.state_dir = state_dir
        self.registry = registry
        self.store = store
        self.coordinator = coordinator
        self.on_pending = on_pending
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event = threading.Event()
        self._sweeper: threading.Thread | None = None

    def start_sweeper(self) -> None:
        if self._sweeper and self._sweeper.is_alive():
            return
        self._sweeper = threading.Thread(
            target=self._sweep_loop, name="mentat-broker-idle", daemon=True
        )
        self._sweeper.start()

    def stop_sweeper(self) -> None:
        self._stop_event.set()
        if self._sweeper:
            self._sweeper.join(timeout=3)

    def endpoint_config_path(self, model: ModelSpec) -> Path:
        if not model.endpoint_config:
            raise SessionError(f"{model.id} has no endpoint configuration")
        return self.root / model.endpoint_config

    def endpoint_state_path(self, model: ModelSpec) -> Path:
        if not model.state_name:
            raise SessionError(f"{model.id} has no endpoint state name")
        return self.state_dir / model.state_name

    def endpoint_url(self, model: ModelSpec) -> str | None:
        override_name = "MENTAT_ENDPOINT_" + model.id.upper().replace("-", "_")
        override = os.getenv(override_name)
        if override:
            return override.rstrip("/")
        if model.id == "kimi-k2.7-code" and os.getenv("MENTAT_PRIMARY_UPSTREAM_URL"):
            return os.environ["MENTAT_PRIMARY_UPSTREAM_URL"].rstrip("/")
        if not model.endpoint_config:
            return None
        try:
            config = json.loads(self.endpoint_config_path(model).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return str(config.get("openai_base_url") or "").rstrip("/") or None

    def _lifecycle(
        self,
        model: ModelSpec,
        command: str,
        *extra: str,
        config_path: Path | None = None,
    ) -> None:
        script = self.root / "scripts" / "mentat" / "vast_endpoint.py"
        args = [
            sys.executable,
            str(script),
            "--config",
            str(config_path or self.endpoint_config_path(model)),
            "--state",
            str(self.endpoint_state_path(model)),
            command,
            *extra,
        ]
        environment = os.environ.copy()
        api_key = environment.get(model.api_key_env) or environment.get("VAST_API_KEY")
        if not api_key:
            raise SessionError("VAST_API_KEY is not available to the broker")
        environment["VAST_API_KEY"] = api_key
        result = subprocess.run(
            args,
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            raise SessionError(details or f"endpoint lifecycle command failed: {command}")

    def _approved_config(self, model: ModelSpec, decision: Decision) -> Path:
        """Pin endpoint search to the approved live price ceiling.

        Vast Serverless chooses a compatible worker rather than renting the exact
        offer returned by discovery. This temporary config ensures the worker
        cannot exceed the price the user approved.
        """
        source = self.endpoint_config_path(model)
        if not decision.offer:
            return source
        try:
            config = json.loads(source.read_text(encoding="utf-8"))
            workergroup = dict(config["workergroup"])
            search_params = str(workergroup.get("search_params") or "")
        except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SessionError(f"invalid endpoint profile for {model.id}: {exc}") from exc
        approved_cap = min(
            decision.offer.hourly_usd,
            decision.max_hourly_usd,
            model.max_hourly_usd,
        )
        replacement = f"dph_total<={approved_cap:.4f}"
        if re.search(r"dph_total\s*<=\s*[^ ]+", search_params):
            search_params = re.sub(r"dph_total\s*<=\s*[^ ]+", replacement, search_params)
        else:
            search_params = f"{search_params} {replacement}".strip()
        workergroup["search_params"] = search_params
        config["workergroup"] = workergroup
        config.setdefault("policy", {})["max_hourly_usd"] = approved_cap
        target = self.state_dir / f"approved-{model.id}-{decision.id}.json"
        target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        return target

    def approve(self, decision: Decision, *, accept_benchmark_cost: bool) -> Decision:
        model = self.registry.get(decision.selected_model)
        if decision.status != "pending":
            return decision
        now = datetime.now(UTC)
        approved_until = now + timedelta(hours=self.registry.policy.max_session_hours)
        endpoint_url = self.endpoint_url(model)

        if model.provider == "external":
            self.store.upsert_session(
                model.id,
                status="ready",
                endpoint_url=endpoint_url,
                decision_id=decision.id,
                started_at=utc_now(),
                last_used_at=utc_now(),
                approved_until=approved_until.isoformat(),
            )
            updated = self.store.update_decision_status(
                decision.id, "approved", approved_at=utc_now()
            )
            self.coordinator.notify()
            if not updated:
                raise SessionError("decision disappeared during approval")
            return updated

        state_path = self.endpoint_state_path(model)
        approved_config = self._approved_config(model, decision)
        self.store.update_decision_status(decision.id, "warming", approved_at=utc_now())
        self.store.upsert_session(
            model.id,
            status="warming",
            endpoint_url=endpoint_url,
            hourly_usd=decision.offer.hourly_usd if decision.offer else None,
            offer=decision.offer,
            decision_id=decision.id,
            started_at=utc_now(),
            last_used_at=utc_now(),
            approved_until=approved_until.isoformat(),
        )
        try:
            if state_path.exists():
                self._lifecycle(model, "warm", config_path=approved_config)
            else:
                if not accept_benchmark_cost:
                    raise SessionError(
                        "Creating a new Vast endpoint requires explicit benchmark-cost acknowledgement"
                    )
                self._lifecycle(
                    model,
                    "create",
                    "--accept-test-worker-cost",
                    config_path=approved_config,
                )
                self._lifecycle(model, "warm", config_path=approved_config)
        except Exception as exc:
            self.store.update_decision_status(decision.id, "failed", error=str(exc))
            self.store.upsert_session(model.id, status="failed", error=str(exc))
            self.coordinator.notify()
            raise

        updated = self.store.update_decision_status(decision.id, "approved")
        self.coordinator.notify()
        if not updated:
            raise SessionError("decision disappeared during approval")
        return updated

    def reject(self, decision_id: str) -> Decision | None:
        updated = self.store.update_decision_status(decision_id, "rejected", completed_at=utc_now())
        self.coordinator.notify()
        return updated

    def is_approved(self, model_id: str) -> bool:
        session = self.store.get_session(model_id)
        if not session or session["status"] not in {"approved", "warming", "ready"}:
            return False
        approved_until = session.get("approved_until")
        if not approved_until:
            return False
        try:
            return datetime.fromisoformat(approved_until) > datetime.now(UTC)
        except ValueError:
            return False

    def wait_until_ready(self, model: ModelSpec, timeout_seconds: int | None = None) -> str:
        endpoint_url = self.endpoint_url(model)
        if not endpoint_url:
            raise SessionError(f"no endpoint URL is configured for {model.id}")
        timeout = timeout_seconds or self.registry.policy.endpoint_ready_timeout_seconds
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._probe(endpoint_url):
                now = utc_now()
                self.store.upsert_session(
                    model.id,
                    status="ready",
                    endpoint_url=endpoint_url,
                    last_used_at=now,
                )
                return endpoint_url
            time.sleep(2)
        raise SessionError(f"timed out waiting for {model.display_name} endpoint: {endpoint_url}")

    def touch(self, model_id: str) -> None:
        session = self.store.get_session(model_id)
        self.store.upsert_session(
            model_id,
            status=(session or {}).get("status", "ready"),
            endpoint_url=(session or {}).get("endpoint_url"),
            last_used_at=utc_now(),
        )

    def ready_fallbacks(self, model: ModelSpec) -> list[ModelSpec]:
        result = []
        for fallback_id in model.fallback_chain:
            fallback = self.registry.get(fallback_id)
            if self.is_approved(fallback.id):
                result.append(fallback)
        return result

    def _probe(self, base_url: str) -> bool:
        targets = [
            base_url.rstrip("/") + "/models",
            base_url.rstrip("/").removesuffix("/v1") + "/health",
        ]
        for target in targets:
            request = urllib.request.Request(
                target, method="GET", headers={"Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    if 200 <= response.status < 500:
                        return True
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue
        return False

    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(30):
            now = datetime.now(UTC)
            for session in self.store.list_sessions():
                if session["status"] not in {"approved", "ready"}:
                    continue
                last_used_raw = session.get("last_used_at")
                if not last_used_raw:
                    continue
                try:
                    last_used = datetime.fromisoformat(last_used_raw)
                except ValueError:
                    continue
                idle_minutes = (now - last_used).total_seconds() / 60
                if idle_minutes < self.registry.policy.idle_shutdown_minutes:
                    continue
                model = self.registry.get(session["model_id"])
                if model.provider != "vast":
                    continue
                try:
                    self._lifecycle(model, "cool")
                    self.store.upsert_session(model.id, status="cooled")
                except Exception as exc:
                    self.store.upsert_session(model.id, status="failed", error=str(exc))
