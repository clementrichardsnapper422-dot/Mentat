from __future__ import annotations

import os
import re
from pathlib import Path

from .models import ModelSpec
from .production_sessions import ProductionSessionManager
from .sessions import EndpointSessionManager


def endpoint_override_name(model_id: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", model_id.upper()).strip("_")
    return f"MENTAT_ENDPOINT_{normalized}"


def install_endpoint_override_hooks() -> None:
    """Install endpoint overrides and the one-authority production boundary."""

    if not getattr(ProductionSessionManager, "_mentat_endpoint_override_installed", False):
        base_endpoint_url = EndpointSessionManager.endpoint_url
        base_reconcile = ProductionSessionManager._reconcile_saved_state

        def endpoint_url(self: ProductionSessionManager, model: ModelSpec) -> str | None:
            override = os.getenv(endpoint_override_name(model.id))
            if override:
                return override.rstrip("/")
            return base_endpoint_url(self, model)

        def reconcile_saved_state(
            self: ProductionSessionManager,
            model: ModelSpec,
            config_path: Path,
        ) -> bool:
            state_path = self.endpoint_state_path(model)
            if state_path.exists() and os.getenv(endpoint_override_name(model.id)):
                return True
            return base_reconcile(self, model, config_path)

        ProductionSessionManager.endpoint_url = endpoint_url  # type: ignore[method-assign]
        ProductionSessionManager._reconcile_saved_state = reconcile_saved_state  # type: ignore[method-assign]
        ProductionSessionManager._mentat_endpoint_override_installed = True  # type: ignore[attr-defined]

    # Imported here to avoid the production-module import cycle.  At runtime this
    # function is called only after MentatV1ProductionApplication is defined.
    from .single_authority import install_single_authority_hooks

    install_single_authority_hooks()
