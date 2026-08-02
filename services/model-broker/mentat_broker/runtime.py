"""Mentat 1.0 broker control-plane facade."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Iterable

from .backends import BackendRegistry, ExperimentalDirectBackend, FakeBackend
from .contracts import RoutingMode, utc_now
from .execution import ExecutionStore
from .intelligence import RouteEngine, TaskAnalyzer
from .release import ReleaseEvidence, ReleaseEvidenceStore
from .spend import BudgetPolicy, SpendGovernor


class MentatV1Runtime:
    """Owns the release-critical local state without provider credentials."""

    def __init__(
        self,
        data_dir: Path,
        *,
        budget_policy: BudgetPolicy | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        secret = self._load_or_create_secret(self.data_dir / "spend-authority.key")
        self.spend = SpendGovernor(
            self.data_dir / "spend.sqlite3",
            signing_secret=secret,
            policy=budget_policy,
        )
        self.executions = ExecutionStore(self.data_dir / "executions.sqlite3")
        self.release = ReleaseEvidenceStore(self.data_dir / "release-evidence.json")
        self.analyzer = TaskAnalyzer()
        self.routes = RouteEngine()
        self.backends = BackendRegistry()
        self.backends.register(FakeBackend())
        self.backends.register(ExperimentalDirectBackend())
        self.recovery_plan = self.executions.startup_recovery_plan()

    @staticmethod
    def _load_or_create_secret(path: Path) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            value = path.read_bytes()
        except FileNotFoundError:
            value = secrets.token_bytes(32)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            descriptor = os.open(path, flags, 0o600)
            try:
                os.write(descriptor, value)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.chmod(path, 0o600)
            except OSError:
                # Windows ACL protection is applied by the installer/runtime boundary.
                pass
        if len(value) != 32:
            raise RuntimeError("spend-authority key has an invalid length")
        return value

    def close(self) -> None:
        self.executions.close()
        self.spend.close()

    def status(self) -> dict[str, Any]:
        release = self.release.report()
        return {
            "product": "Mentat",
            "target_version": "1.0.0",
            "broker_contract_version": 1,
            "paid_compute_kill_switch": self.spend.kill_switch_enabled(),
            "spend": self.spend.snapshot(),
            "executions": [item.as_dict() for item in self.executions.list(limit=25)],
            "startup_recovery_plan": list(self.recovery_plan),
            "backends": self.backends.describe(),
            "circuits": self.routes.circuits.describe(),
            "release": release,
        }

    def analyze_task(
        self,
        prompt: str,
        *,
        input_tokens: int = 0,
        reserved_output_tokens: int = 4096,
        tool_names: Iterable[str] = (),
        repository_files: int = 0,
        attachment_bytes: int = 0,
        has_images: bool = False,
        routing_mode: str = "balanced",
        maximum_total_cost_usd: float = 64.0,
        maximum_latency_ms: int = 30 * 60 * 1000,
    ) -> dict[str, Any]:
        requirements = self.analyzer.analyze(
            prompt,
            input_tokens=input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            tool_names=tool_names,
            repository_files=repository_files,
            attachment_bytes=attachment_bytes,
            has_images=has_images,
            routing_mode=RoutingMode(routing_mode),
            maximum_total_cost_usd=maximum_total_cost_usd,
            maximum_latency_ms=maximum_latency_ms,
        )
        return requirements.as_dict()

    def set_kill_switch(
        self,
        enabled: bool,
        *,
        reason: str,
        actor: str = "desktop-admin",
    ) -> dict[str, Any]:
        self.spend.set_kill_switch(enabled, reason=reason, actor=actor)
        return self.spend.snapshot()

    def record_automated_release_evidence(
        self,
        requirement_id: str,
        *,
        source: str,
        artifact: str | None = None,
        sha256: str | None = None,
        notes: str | None = None,
    ) -> None:
        self.release.record(
            ReleaseEvidence(
                requirement_id=requirement_id,
                status="passed",
                observed_at=utc_now(),
                source=source,
                artifact=artifact,
                sha256=sha256,
                notes=notes,
                actor="automated-acceptance",
            )
        )
