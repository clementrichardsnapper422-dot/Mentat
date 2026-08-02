"""Dynamic model controls that cannot erase existing provider state."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .models import ModelConfig, Registry
from .settings import DesktopSettingsStore


class ModelDisabledError(KeyError):
    """Raised when a disabled model is requested for a new execution."""


class SettingsAwareRegistry:
    """Filter new model selection while delegating immutable registry policy.

    Existing session and provider lifecycle managers intentionally retain the original
    registry so a disabled model can still be cooled, reconciled, or destroyed safely.
    """

    def __init__(self, base: Registry, settings: DesktopSettingsStore) -> None:
        self._base = base
        self._settings = settings

    @property
    def path(self):
        return self._base.path

    @property
    def schema_version(self) -> int:
        return self._base.schema_version

    @property
    def policy(self):
        return self._base.policy

    @property
    def models(self) -> tuple[ModelConfig, ...]:
        disabled = set(self._settings.load().disabled_model_ids)
        return tuple(model for model in self._base.models if model.id not in disabled)

    def get(self, model_id: str) -> ModelConfig:
        if model_id in set(self._settings.load().disabled_model_ids):
            raise ModelDisabledError(f"model is disabled: {model_id}")
        return self._base.get(model_id)

    def all_models(self) -> tuple[ModelConfig, ...]:
        """Return every declared profile for UI/status without enabling selection."""

        return tuple(self._base.models)

    def enabled_ids(self) -> frozenset[str]:
        return frozenset(model.id for model in self.models)

    def __iter__(self) -> Iterator[ModelConfig]:
        return iter(self.models)

    def __len__(self) -> int:
        return len(self.models)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)
