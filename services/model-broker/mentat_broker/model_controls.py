"""Dynamic model controls that cannot erase existing provider state."""

from __future__ import annotations

from typing import Any

from .models import ModelSpec
from .registry import ModelRegistry
from .settings import DesktopSettingsStore


class ModelDisabledError(KeyError):
    """Raised when a disabled model is requested for a new execution."""


class SettingsAwareRegistry:
    """Filter new routing while preserving the immutable lifecycle registry.

    The production application gives this view to routing and keeps the original
    ``ModelRegistry`` inside the session manager. A disabled model therefore
    cannot receive new work, but an existing paid resource can still be observed,
    cooled, reconciled, or destroyed.
    """

    def __init__(self, base: ModelRegistry, settings: DesktopSettingsStore) -> None:
        self._base = base
        self._settings = settings

    @property
    def policy(self):
        return self._base.policy

    @property
    def source(self):
        return self._base.source

    @property
    def root(self):
        return self._base.root

    def get(self, model_id: str) -> ModelSpec:
        if model_id in self._disabled_ids():
            raise ModelDisabledError(f"model is disabled: {model_id}")
        return self._base.get(model_id)

    def enabled(self) -> list[ModelSpec]:
        disabled = self._disabled_ids()
        return [model for model in self._base.enabled() if model.id not in disabled]

    def all(self) -> list[ModelSpec]:
        """Return every model for status without making it routing-eligible."""

        return self._base.all()

    def all_models(self) -> tuple[ModelSpec, ...]:
        return tuple(self._base.all())

    def enabled_ids(self) -> frozenset[str]:
        return frozenset(model.id for model in self.enabled())

    def as_public_dict(self) -> dict[str, Any]:
        payload = self._base.as_public_dict()
        payload["disabled_model_ids"] = sorted(self._disabled_ids())
        payload["enabled_model_ids"] = sorted(self.enabled_ids())
        return payload

    def _disabled_ids(self) -> set[str]:
        return set(self._settings.load().disabled_model_ids)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)
