"""Durable, validated user settings for the Mentat 1.0 desktop product."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .contracts import RoutingMode, utc_now

PrivacyMode = Literal["local_first", "remote_allowed"]


@dataclass(frozen=True)
class BudgetSettings:
    maximum_hourly_usd: float = 4.0
    maximum_session_usd: float = 12.0
    maximum_daily_usd: float = 25.0
    maximum_monthly_usd: float = 100.0
    maximum_retry_usd: float = 2.0
    maximum_fallback_usd: float = 4.0
    maximum_exploration_usd: float = 1.0

    def validate(self) -> None:
        values = asdict(self)
        for name, value in values.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{name} must be a non-negative number")
        if self.maximum_hourly_usd <= 0:
            raise ValueError("maximum_hourly_usd must be positive")
        if self.maximum_session_usd <= 0:
            raise ValueError("maximum_session_usd must be positive")
        if self.maximum_daily_usd < self.maximum_session_usd:
            raise ValueError("maximum_daily_usd cannot be below the session ceiling")
        if self.maximum_monthly_usd < self.maximum_daily_usd:
            raise ValueError("maximum_monthly_usd cannot be below the daily ceiling")
        if self.maximum_retry_usd > self.maximum_session_usd:
            raise ValueError("maximum_retry_usd cannot exceed the session ceiling")
        if self.maximum_fallback_usd > self.maximum_session_usd:
            raise ValueError("maximum_fallback_usd cannot exceed the session ceiling")
        if self.maximum_exploration_usd > self.maximum_session_usd:
            raise ValueError("maximum_exploration_usd cannot exceed the session ceiling")


@dataclass(frozen=True)
class DesktopSettings:
    schema_version: int = 1
    setup_completed: bool = False
    setup_completed_at: str | None = None
    workspace: str = ""
    privacy_mode: PrivacyMode = "local_first"
    remote_inference_enabled: bool = False
    routing_mode: RoutingMode = RoutingMode.BALANCED
    one_paid_session: bool = True
    disabled_model_ids: tuple[str, ...] = ()
    budgets: BudgetSettings = field(default_factory=BudgetSettings)
    update_channel: Literal["stable", "release_candidate"] = "stable"
    preserve_user_data_on_uninstall: bool = True
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported desktop settings schema")
        if self.privacy_mode not in {"local_first", "remote_allowed"}:
            raise ValueError("privacy_mode is invalid")
        if self.update_channel not in {"stable", "release_candidate"}:
            raise ValueError("update_channel is invalid")
        if self.remote_inference_enabled and self.privacy_mode != "remote_allowed":
            raise ValueError(
                "remote inference cannot be enabled while privacy_mode is local_first"
            )
        if self.setup_completed:
            if not self.workspace.strip():
                raise ValueError("a workspace is required before setup can complete")
            workspace = Path(self.workspace).expanduser()
            if not workspace.is_absolute():
                raise ValueError("workspace must be an absolute path")
        if any(not item.strip() for item in self.disabled_model_ids):
            raise ValueError("disabled_model_ids cannot contain empty values")
        self.budgets.validate()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["routing_mode"] = self.routing_mode.value
        value["disabled_model_ids"] = list(self.disabled_model_ids)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DesktopSettings:
        budgets_raw = value.get("budgets") or {}
        settings = cls(
            schema_version=int(value.get("schema_version", 1)),
            setup_completed=bool(value.get("setup_completed", False)),
            setup_completed_at=(
                str(value["setup_completed_at"])
                if value.get("setup_completed_at")
                else None
            ),
            workspace=str(value.get("workspace") or ""),
            privacy_mode=str(value.get("privacy_mode") or "local_first"),  # type: ignore[arg-type]
            remote_inference_enabled=bool(
                value.get("remote_inference_enabled", False)
            ),
            routing_mode=RoutingMode(value.get("routing_mode") or "balanced"),
            one_paid_session=bool(value.get("one_paid_session", True)),
            disabled_model_ids=tuple(
                sorted({str(item) for item in value.get("disabled_model_ids", [])})
            ),
            budgets=BudgetSettings(
                maximum_hourly_usd=float(
                    budgets_raw.get("maximum_hourly_usd", 4.0)
                ),
                maximum_session_usd=float(
                    budgets_raw.get("maximum_session_usd", 12.0)
                ),
                maximum_daily_usd=float(
                    budgets_raw.get("maximum_daily_usd", 25.0)
                ),
                maximum_monthly_usd=float(
                    budgets_raw.get("maximum_monthly_usd", 100.0)
                ),
                maximum_retry_usd=float(
                    budgets_raw.get("maximum_retry_usd", 2.0)
                ),
                maximum_fallback_usd=float(
                    budgets_raw.get("maximum_fallback_usd", 4.0)
                ),
                maximum_exploration_usd=float(
                    budgets_raw.get("maximum_exploration_usd", 1.0)
                ),
            ),
            update_channel=str(value.get("update_channel") or "stable"),  # type: ignore[arg-type]
            preserve_user_data_on_uninstall=bool(
                value.get("preserve_user_data_on_uninstall", True)
            ),
            created_at=str(value.get("created_at") or utc_now()),
            updated_at=str(value.get("updated_at") or utc_now()),
        )
        settings.validate()
        return settings


class DesktopSettingsStore:
    ALLOWED_PATCH_FIELDS = {
        "workspace",
        "privacy_mode",
        "remote_inference_enabled",
        "routing_mode",
        "one_paid_session",
        "disabled_model_ids",
        "budgets",
        "update_channel",
        "preserve_user_data_on_uninstall",
    }

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(DesktopSettings())
        else:
            self.load()

    def load(self) -> DesktopSettings:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"desktop settings are unreadable: {exc}") from exc
            if not isinstance(raw, dict):
                raise RuntimeError("desktop settings must be a JSON object")
            return DesktopSettings.from_dict(raw)

    def preview_update(self, patch: dict[str, Any]) -> DesktopSettings:
        unknown = set(patch) - self.ALLOWED_PATCH_FIELDS
        if unknown:
            raise ValueError(f"unsupported settings fields: {sorted(unknown)}")
        current = self.load().as_dict()
        for key, value in patch.items():
            if key == "budgets":
                if not isinstance(value, dict):
                    raise ValueError("budgets must be an object")
                current["budgets"] = {**current["budgets"], **value}
            else:
                current[key] = value
        current["updated_at"] = utc_now()
        return DesktopSettings.from_dict(current)

    def preview_complete_setup(self, patch: dict[str, Any]) -> DesktopSettings:
        candidate = self.preview_update(patch).as_dict()
        candidate["setup_completed"] = True
        candidate["setup_completed_at"] = utc_now()
        candidate["updated_at"] = utc_now()
        return DesktopSettings.from_dict(candidate)

    def replace(self, settings: DesktopSettings) -> DesktopSettings:
        self._write(settings)
        return settings

    def update(self, patch: dict[str, Any]) -> DesktopSettings:
        return self.replace(self.preview_update(patch))

    def complete_setup(self, patch: dict[str, Any]) -> DesktopSettings:
        return self.replace(self.preview_complete_setup(patch))

    def reset_setup(self) -> DesktopSettings:
        current = self.load().as_dict()
        current["setup_completed"] = False
        current["setup_completed_at"] = None
        current["updated_at"] = utc_now()
        return self.replace(DesktopSettings.from_dict(current))

    def _write(self, settings: DesktopSettings) -> None:
        settings.validate()
        with self._lock:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=self.path.parent,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(settings.as_dict(), stream, indent=2, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
