"""Mentat 1.0 broker control-plane facade."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

from .backends import BackendRegistry, ExperimentalDirectBackend, FakeBackend
from .contracts import RoutingMode, utc_now
from .diagnostics import DiagnosticsService
from .execution import ExecutionStore
from .intelligence import RouteEngine, TaskAnalyzer
from .release import ReleaseEvidence, ReleaseEvidenceStore
from .settings import DesktopSettings, DesktopSettingsStore
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
        self.hard_budget_policy = budget_policy or BudgetPolicy()
        secret = self._load_or_create_secret(self.data_dir / "spend-authority.key")
        self.spend = SpendGovernor(
            self.data_dir / "spend.sqlite3",
            signing_secret=secret,
            policy=self.hard_budget_policy,
        )
        self.executions = ExecutionStore(self.data_dir / "executions.sqlite3")
        self.release = ReleaseEvidenceStore(self.data_dir / "release-evidence.json")
        self.settings = DesktopSettingsStore(self.data_dir / "desktop-settings.json")
        self.diagnostics = DiagnosticsService(self.data_dir)
        self.analyzer = TaskAnalyzer()
        self.routes = RouteEngine()
        self.backends = BackendRegistry()
        self.backends.register(FakeBackend())
        self.backends.register(ExperimentalDirectBackend())
        self.recovery_plan = self.executions.startup_recovery_plan()
        self._validate_settings_against_hard_policy(self.settings.load())

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
            with suppress(OSError):
                os.chmod(path, 0o600)
        if len(value) != 32:
            raise RuntimeError("spend-authority key has an invalid length")
        return value

    def close(self) -> None:
        self.executions.close()
        self.spend.close()

    def status(self) -> dict[str, Any]:
        release = self.release.report()
        settings = self.settings.load()
        diagnostics = self.diagnostics.run(include_docker=False)
        return {
            "product": "Mentat",
            "target_version": "1.0.0",
            "broker_contract_version": 1,
            "paid_compute_kill_switch": self.spend.kill_switch_enabled(),
            "setup": {
                "completed": settings.setup_completed,
                "completed_at": settings.setup_completed_at,
            },
            "settings": settings.as_dict(),
            "effective_budget_ceiling": self._effective_budget_ceiling(settings),
            "diagnostics": {
                "passed": diagnostics["passed"],
                "repairable_failures": diagnostics["repairable_failures"],
            },
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
        routing_mode: str | None = None,
        maximum_total_cost_usd: float | None = None,
        maximum_latency_ms: int = 30 * 60 * 1000,
    ) -> dict[str, Any]:
        settings = self.settings.load()
        selected_mode = RoutingMode(routing_mode or settings.routing_mode.value)
        configured_session = min(
            settings.budgets.maximum_session_usd,
            self.hard_budget_policy.maximum_session_usd,
        )
        selected_cost = (
            configured_session
            if maximum_total_cost_usd is None
            else min(float(maximum_total_cost_usd), configured_session)
        )
        requirements = self.analyzer.analyze(
            prompt,
            input_tokens=input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            tool_names=tool_names,
            repository_files=repository_files,
            attachment_bytes=attachment_bytes,
            has_images=has_images,
            routing_mode=selected_mode,
            maximum_total_cost_usd=selected_cost,
            maximum_latency_ms=maximum_latency_ms,
        )
        return requirements.as_dict()

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        candidate = self.settings.preview_update(patch)
        self._validate_settings_against_hard_policy(candidate)
        return self.settings.replace(candidate).as_dict()

    def complete_setup(self, patch: dict[str, Any]) -> dict[str, Any]:
        candidate = self.settings.preview_complete_setup(patch)
        self._validate_settings_against_hard_policy(candidate)
        workspace = Path(candidate.workspace).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        if not workspace.is_dir():
            raise RuntimeError("configured workspace is not a directory")
        return self.settings.replace(candidate).as_dict()

    def reset_setup(self) -> dict[str, Any]:
        return self.settings.reset_setup().as_dict()

    def run_diagnostics(self, *, include_docker: bool = True) -> dict[str, Any]:
        return self.diagnostics.run(include_docker=include_docker)

    def safe_repair(self) -> dict[str, Any]:
        return self.diagnostics.safe_repair()

    def create_backup(self) -> dict[str, Any]:
        return self.diagnostics.create_backup()

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

    def _validate_settings_against_hard_policy(self, settings: DesktopSettings) -> None:
        hard = self.hard_budget_policy
        configured = settings.budgets
        pairs = {
            "maximum_hourly_usd": (
                configured.maximum_hourly_usd,
                hard.maximum_hourly_usd,
            ),
            "maximum_session_usd": (
                configured.maximum_session_usd,
                hard.maximum_session_usd,
            ),
            "maximum_daily_usd": (
                configured.maximum_daily_usd,
                hard.maximum_daily_usd,
            ),
            "maximum_monthly_usd": (
                configured.maximum_monthly_usd,
                hard.maximum_monthly_usd,
            ),
            "maximum_retry_usd": (
                configured.maximum_retry_usd,
                hard.maximum_retry_usd,
            ),
            "maximum_fallback_usd": (
                configured.maximum_fallback_usd,
                hard.maximum_fallback_usd,
            ),
            "maximum_exploration_usd": (
                configured.maximum_exploration_usd,
                hard.maximum_exploration_usd,
            ),
        }
        violations = [name for name, (value, ceiling) in pairs.items() if value > ceiling]
        if violations:
            raise ValueError(
                "desktop settings exceed immutable registry policy: "
                + ", ".join(sorted(violations))
            )

    def _effective_budget_ceiling(self, settings: DesktopSettings) -> dict[str, float]:
        hard = self.hard_budget_policy
        configured = settings.budgets
        return {
            "maximum_hourly_usd": min(configured.maximum_hourly_usd, hard.maximum_hourly_usd),
            "maximum_session_usd": min(configured.maximum_session_usd, hard.maximum_session_usd),
            "maximum_daily_usd": min(configured.maximum_daily_usd, hard.maximum_daily_usd),
            "maximum_monthly_usd": min(configured.maximum_monthly_usd, hard.maximum_monthly_usd),
            "maximum_retry_usd": min(configured.maximum_retry_usd, hard.maximum_retry_usd),
            "maximum_fallback_usd": min(configured.maximum_fallback_usd, hard.maximum_fallback_usd),
            "maximum_exploration_usd": min(
                configured.maximum_exploration_usd,
                hard.maximum_exploration_usd,
            ),
        }
