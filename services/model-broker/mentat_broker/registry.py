from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BrokerPolicy, ModelSpec

VALID_TASK_CLASSES = {"simple", "general", "code", "large_code", "vision", "high_risk"}
VALID_CAPABILITIES = {"reasoning", "coding", "tools", "vision", "long_context"}
VALID_PROVIDERS = {"vast", "external"}


class RegistryError(RuntimeError):
    """Raised when the model registry is invalid."""


class ModelRegistry:
    def __init__(self, policy: BrokerPolicy, models: list[ModelSpec], source: Path):
        self.policy = policy
        self.source = source.resolve()
        self.root = self.source.parent.parent
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
        if not all(isinstance(item, dict) for item in raw_models):
            raise RegistryError("every model registry entry must be an object")
        models = [ModelSpec.from_dict(dict(item)) for item in raw_models]
        return cls(policy=policy, models=models, source=path)

    def _validate_policy(self) -> None:
        policy = self.policy
        if not 1 <= policy.port <= 65535:
            raise RegistryError("policy.port must be between 1 and 65535")
        if policy.max_hourly_usd <= 0 or policy.max_session_hours <= 0:
            raise RegistryError("hourly and session limits must be positive")
        if policy.max_total_usd <= 0:
            raise RegistryError("policy.max_total_usd must be positive")
        if policy.idle_shutdown_minutes < 1:
            raise RegistryError("policy.idle_shutdown_minutes must be at least 1")
        if policy.approval_timeout_seconds < 10:
            raise RegistryError("policy.approval_timeout_seconds must be at least 10")
        if policy.endpoint_ready_timeout_seconds < 30:
            raise RegistryError("policy.endpoint_ready_timeout_seconds must be at least 30")
        if not 0 <= policy.minimum_reliability <= 1:
            raise RegistryError("policy.minimum_reliability must be between 0 and 1")
        if not 1 <= policy.max_concurrent_requests <= 64:
            raise RegistryError("policy.max_concurrent_requests must be between 1 and 64")
        if not 1024 <= policy.max_request_body_bytes <= 64 * 1024 * 1024:
            raise RegistryError("policy.max_request_body_bytes is outside the supported range")
        if policy.shutdown_cooldown_timeout_seconds < 10:
            raise RegistryError("policy.shutdown_cooldown_timeout_seconds must be at least 10")

    def _validate(self) -> None:
        self._validate_policy()
        if self.policy.primary_model_id not in self._models:
            raise RegistryError("policy.primary_model_id does not identify a registered model")
        primary = self._models[self.policy.primary_model_id]
        if not primary.enabled:
            raise RegistryError("the primary model must be enabled")

        for model in self._models.values():
            if not model.id or not model.model_id or not model.display_name:
                raise RegistryError("each model needs id, model_id, and display_name")
            if model.provider not in VALID_PROVIDERS:
                raise RegistryError(f"{model.id}: unsupported provider {model.provider}")
            if model.quality_tier < 1 or model.quality_tier > 5:
                raise RegistryError(f"{model.id}: quality_tier must be between 1 and 5")
            if model.context_tokens < 1024:
                raise RegistryError(f"{model.id}: context_tokens must be at least 1024")
            if model.minimum_benchmark_samples < 1:
                raise RegistryError(f"{model.id}: minimum_benchmark_samples must be positive")
            if model.max_hourly_usd < 0 or model.max_hourly_usd > self.policy.max_hourly_usd:
                raise RegistryError(
                    f"{model.id}: max_hourly_usd must be between 0 and the global cap"
                )
            if not model.task_classes or not model.task_classes.issubset(VALID_TASK_CLASSES):
                raise RegistryError(f"{model.id}: invalid or empty task_classes")
            if not model.capabilities or not model.capabilities.issubset(VALID_CAPABILITIES):
                raise RegistryError(f"{model.id}: invalid or empty capabilities")
            if (
                self.policy.serverless_text_only
                and model.provider == "vast"
                and ("vision" in model.capabilities or "vision" in model.task_classes)
            ):
                raise RegistryError(
                    f"{model.id}: Vast Serverless is configured text-only; vision must be disabled"
                )
            for task_class, score in model.bootstrap_quality.items():
                if task_class not in VALID_TASK_CLASSES or not 0 <= score <= 1:
                    raise RegistryError(f"{model.id}: invalid bootstrap quality for {task_class}")
            for task_class in model.task_classes:
                if task_class not in model.default_minutes:
                    raise RegistryError(f"{model.id}: missing default_minutes for {task_class}")
                if model.default_minutes[task_class] <= 0:
                    raise RegistryError(f"{model.id}: default minutes must be positive")

            if model.provider == "vast":
                if not model.endpoint_config or not model.state_name:
                    raise RegistryError(f"{model.id}: Vast models need endpoint_config and state_name")
                if model.num_gpus < 1 or model.min_gpu_ram_mb < 1 or model.min_disk_gb < 1:
                    raise RegistryError(f"{model.id}: Vast models need GPU, RAM, and disk requirements")
                if model.max_hourly_usd <= 0:
                    raise RegistryError(f"{model.id}: max_hourly_usd must be positive")
                endpoint_path = (self.root / model.endpoint_config).resolve()
                try:
                    endpoint_path.relative_to(self.root)
                except ValueError as exc:
                    raise RegistryError(f"{model.id}: endpoint_config escapes the repository") from exc
                if not endpoint_path.is_file():
                    raise RegistryError(f"{model.id}: endpoint config not found: {model.endpoint_config}")

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
            "source": self.source.name,
            "policy": self.policy.__dict__,
            "models": [model.as_public_dict() for model in self.all()],
        }
