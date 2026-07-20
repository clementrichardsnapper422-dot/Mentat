from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BrokerPolicy, ModelSpec


class RegistryError(RuntimeError):
    """Raised when the model registry is invalid."""


class ModelRegistry:
    def __init__(self, policy: BrokerPolicy, models: list[ModelSpec], source: Path):
        self.policy = policy
        self.source = source
        self._models = {model.id: model for model in models}
        if len(self._models) != len(models):
            raise RegistryError("model IDs must be unique")
        self._validate()

    @classmethod
    def load(cls, path: Path) -> ModelRegistry:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RegistryError(f"model registry not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RegistryError(f"invalid model registry JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise RegistryError("model registry root must be an object")
        policy = BrokerPolicy.from_dict(dict(raw.get("policy", {})))
        raw_models = raw.get("models")
        if not isinstance(raw_models, list) or not raw_models:
            raise RegistryError("model registry must contain a non-empty models array")
        models = [ModelSpec.from_dict(dict(item)) for item in raw_models]
        return cls(policy=policy, models=models, source=path)

    def _validate(self) -> None:
        for model in self._models.values():
            if not model.id or not model.model_id:
                raise RegistryError("each model needs id and model_id")
            if model.quality_tier < 1 or model.quality_tier > 5:
                raise RegistryError(f"{model.id}: quality_tier must be between 1 and 5")
            if model.provider == "vast":
                if not model.endpoint_config or not model.state_name:
                    raise RegistryError(f"{model.id}: Vast models need endpoint_config and state_name")
                if model.num_gpus < 1 or model.min_gpu_ram_mb < 1:
                    raise RegistryError(f"{model.id}: Vast models need GPU requirements")
                if model.max_hourly_usd <= 0:
                    raise RegistryError(f"{model.id}: max_hourly_usd must be positive")
            for fallback in model.fallback_chain:
                if fallback not in self._models:
                    raise RegistryError(f"{model.id}: unknown fallback model {fallback}")
                if fallback == model.id:
                    raise RegistryError(f"{model.id}: a model cannot fall back to itself")

    def get(self, model_id: str) -> ModelSpec:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise RegistryError(f"unknown model: {model_id}") from exc

    def enabled(self) -> list[ModelSpec]:
        return [model for model in self._models.values() if model.enabled]

    def all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "policy": self.policy.__dict__,
            "models": [model.as_public_dict() for model in self.all()],
        }
