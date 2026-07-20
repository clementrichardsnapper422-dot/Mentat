from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TaskClass = Literal["simple", "general", "code", "large_code", "vision", "high_risk"]
DecisionStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "warming",
    "ready",
    "failed",
    "completed",
    "timed_out",
]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    model_id: str
    provider: str
    enabled: bool
    quality_tier: int
    bootstrap_quality: dict[str, float]
    capabilities: set[str]
    task_classes: set[str]
    context_tokens: int
    num_gpus: int
    min_gpu_ram_mb: int
    gpu_names: list[str]
    max_hourly_usd: float
    endpoint_config: str | None
    state_name: str | None
    fallback_chain: list[str]
    default_minutes: dict[str, int]
    minimum_benchmark_samples: int = 3
    api_key_env: str = "VAST_API_KEY"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelSpec:
        return cls(
            id=str(data["id"]),
            display_name=str(data["display_name"]),
            model_id=str(data["model_id"]),
            provider=str(data.get("provider", "vast")),
            enabled=bool(data.get("enabled", True)),
            quality_tier=int(data.get("quality_tier", 1)),
            bootstrap_quality={
                str(key): float(value) for key, value in dict(data.get("bootstrap_quality", {})).items()
            },
            capabilities={str(item) for item in data.get("capabilities", [])},
            task_classes={str(item) for item in data.get("task_classes", [])},
            context_tokens=int(data.get("context_tokens", 0)),
            num_gpus=int(data.get("num_gpus", 0)),
            min_gpu_ram_mb=int(data.get("min_gpu_ram_mb", 0)),
            gpu_names=[str(item) for item in data.get("gpu_names", [])],
            max_hourly_usd=float(data.get("max_hourly_usd", 0)),
            endpoint_config=(str(data["endpoint_config"]) if data.get("endpoint_config") else None),
            state_name=(str(data["state_name"]) if data.get("state_name") else None),
            fallback_chain=[str(item) for item in data.get("fallback_chain", [])],
            default_minutes={
                str(key): int(value) for key, value in dict(data.get("default_minutes", {})).items()
            },
            minimum_benchmark_samples=int(data.get("minimum_benchmark_samples", 3)),
            api_key_env=str(data.get("api_key_env", "VAST_API_KEY")),
        )

    def as_public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = sorted(self.capabilities)
        value["task_classes"] = sorted(self.task_classes)
        return value


@dataclass(frozen=True)
class BrokerPolicy:
    port: int = 18890
    max_hourly_usd: float = 32.0
    max_session_hours: float = 4.0
    max_total_usd: float = 64.0
    idle_shutdown_minutes: int = 30
    approval_timeout_seconds: int = 300
    endpoint_ready_timeout_seconds: int = 1800
    minimum_reliability: float = 0.98
    require_manual_approval: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrokerPolicy:
        return cls(
            port=int(data.get("port", 18890)),
            max_hourly_usd=float(data.get("max_hourly_usd", 32.0)),
            max_session_hours=float(data.get("max_session_hours", 4.0)),
            max_total_usd=float(data.get("max_total_usd", 64.0)),
            idle_shutdown_minutes=int(data.get("idle_shutdown_minutes", 30)),
            approval_timeout_seconds=int(data.get("approval_timeout_seconds", 300)),
            endpoint_ready_timeout_seconds=int(data.get("endpoint_ready_timeout_seconds", 1800)),
            minimum_reliability=float(data.get("minimum_reliability", 0.98)),
            require_manual_approval=bool(data.get("require_manual_approval", True)),
        )


@dataclass(frozen=True)
class Offer:
    id: int
    gpu_name: str
    num_gpus: int
    gpu_ram_mb: int
    hourly_usd: float
    reliability: float
    verified: bool
    geolocation: str | None = None
    dlperf: float | None = None

    @classmethod
    def from_vast(cls, raw: dict[str, Any]) -> Offer:
        return cls(
            id=int(raw["id"]),
            gpu_name=str(raw.get("gpu_name") or "unknown"),
            num_gpus=int(raw.get("num_gpus") or 0),
            gpu_ram_mb=int(raw.get("gpu_ram") or 0),
            hourly_usd=float(raw.get("dph_total") or 0),
            reliability=float(raw.get("reliability2") or raw.get("reliability") or 0),
            verified=bool(raw.get("verified", False)),
            geolocation=(str(raw["geolocation"]) if raw.get("geolocation") else None),
            dlperf=(float(raw["dlperf"]) if raw.get("dlperf") is not None else None),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteRequirements:
    task_class: TaskClass
    capabilities: set[str]
    minimum_quality_tier: int
    estimated_input_tokens: int
    risk_level: str
    estimated_minutes: int

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["capabilities"] = sorted(self.capabilities)
        return value


@dataclass
class Decision:
    id: str
    created_at: str
    prompt_preview: str
    prompt_digest: str
    task_class: TaskClass
    selected_model: str
    selected_model_id: str
    fallback_chain: list[str]
    reasons: list[str]
    quality_score: float
    quality_source: str
    benchmark_samples: int
    offer: Offer | None
    offer_source: str
    estimated_minutes: int
    estimated_cost_usd: float
    max_hourly_usd: float
    max_total_usd: float
    status: DecisionStatus = "pending"
    error: str | None = None
    approved_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["offer"] = self.offer.as_dict() if self.offer else None
        return value


@dataclass(frozen=True)
class BenchmarkRecord:
    model_id: str
    task_class: str
    success: bool
    latency_ms: float
    tokens_per_second: float | None
    hourly_usd: float | None
    total_cost_usd: float | None
    quality_score: float | None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
