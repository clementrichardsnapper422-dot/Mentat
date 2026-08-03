"""Provider-neutral typed contracts shared by Mentat 1.0."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _encode(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (set, frozenset, tuple)):
        return [_encode(item) for item in sorted(value)]
    if is_dataclass(value):
        return {key: _encode(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


class RoutingMode(StrEnum):
    BEST = "best"
    BALANCED = "balanced"
    ECONOMY = "economy"
    MANUAL = "manual"


class RiskLevel(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceTier(StrEnum):
    PRIOR = "prior"
    BENCHMARK = "benchmark"
    PRODUCTION = "production"
    LIVE_VALIDATED = "live_validated"


class BackendKind(StrEnum):
    VAST_SERVERLESS = "vast_serverless"
    VAST_DIRECT = "vast_direct"
    LOCAL = "local"
    FAKE = "fake"


class ProviderLifecycle(StrEnum):
    UNKNOWN = "unknown"
    ABSENT = "absent"
    CREATING = "creating"
    WARMING = "warming"
    READY = "ready"
    BUSY = "busy"
    COOLING = "cooling"
    COOLED = "cooled"
    STOPPED = "stopped"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class ExecutionState(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    RESERVING = "reserving"
    ACQUIRING = "acquiring"
    AMBIGUOUS = "ambiguous"
    RECONCILING = "reconciling"
    WARMING = "warming"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    COOLING = "cooling"
    COOLED = "cooled"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class RangeEstimate:
    low: float
    expected: float
    high: float
    unit: str

    def __post_init__(self) -> None:
        if min(self.low, self.expected, self.high) < 0:
            raise ValueError("estimate values cannot be negative")
        if not self.low <= self.expected <= self.high:
            raise ValueError("estimate must satisfy low <= expected <= high")
        if not self.unit:
            raise ValueError("estimate unit is required")

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class TaskRequirements:
    task_class: str
    capabilities: frozenset[str]
    input_tokens: int
    reserved_output_tokens: int
    minimum_quality: float
    minimum_success_probability: float
    maximum_total_cost_usd: float
    maximum_latency_ms: int
    risk_level: RiskLevel = RiskLevel.NORMAL
    verification_strength: str = "standard"
    reversible: bool = True
    blast_radius: str = "workspace"
    repository_files: int = 0
    attachment_bytes: int = 0
    routing_mode: RoutingMode = RoutingMode.BALANCED
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def required_context_tokens(self) -> int:
        return self.input_tokens + self.reserved_output_tokens

    def as_dict(self) -> dict[str, Any]:
        return {**_encode(self), "required_context_tokens": self.required_context_tokens}


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    model_id: str
    model_version: str
    provider: str
    backend: BackendKind
    runtime_revision: str
    capabilities: frozenset[str]
    task_classes: frozenset[str]
    context_tokens: int
    quality_prior: float
    success_prior: float
    production_eligible: bool
    maximum_hourly_usd: float
    minimum_reliability: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class HardwareProfile:
    gpu_name: str
    gpu_count: int
    gpu_ram_mb: int
    verified: bool
    reliability: float
    host_id: str | None = None
    region: str | None = None
    disk_gb: float | None = None
    nvlink_gbps: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ProviderMarketSnapshot:
    snapshot_id: str
    observed_at: str
    backend: BackendKind
    offer_id: str
    hourly_usd: float
    hardware: HardwareProfile
    source: str
    expires_at: str
    raw_digest: str

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ExecutionCandidate:
    candidate_id: str
    profile: ModelProfile
    market: ProviderMarketSnapshot | None
    quality: RangeEstimate
    success_probability: RangeEstimate
    total_cost_usd: RangeEstimate
    latency_ms: RangeEstimate
    evidence_tier: EvidenceTier
    evidence_samples: int
    evidence_observed_at: str | None
    eligible: bool
    hard_rejections: tuple[str, ...] = ()
    score: float | None = None
    score_components: dict[str, float] = field(default_factory=dict)
    exploration: bool = False

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ApprovalLease:
    lease_id: str
    decision_id: str
    subject: str
    issued_at: str
    expires_at: str
    allowed_backend: BackendKind
    allowed_model_id: str
    maximum_hourly_usd: float
    maximum_total_usd: float
    maximum_attempts: int
    fallback_allowed: bool
    nonce: str
    signature: str

    @classmethod
    def issue(
        cls,
        secret: bytes,
        *,
        decision_id: str,
        subject: str,
        expires_at: str,
        allowed_backend: BackendKind,
        allowed_model_id: str,
        maximum_hourly_usd: float,
        maximum_total_usd: float,
        maximum_attempts: int = 1,
        fallback_allowed: bool = False,
        issued_at: str | None = None,
    ) -> ApprovalLease:
        unsigned = {
            "lease_id": secrets.token_hex(16),
            "decision_id": decision_id,
            "subject": subject,
            "issued_at": issued_at or utc_now(),
            "expires_at": expires_at,
            "allowed_backend": allowed_backend.value,
            "allowed_model_id": allowed_model_id,
            "maximum_hourly_usd": float(maximum_hourly_usd),
            "maximum_total_usd": float(maximum_total_usd),
            "maximum_attempts": int(maximum_attempts),
            "fallback_allowed": bool(fallback_allowed),
            "nonce": secrets.token_hex(16),
        }
        signature = hmac.new(
            secret,
            canonical_json(unsigned).encode(),
            hashlib.sha256,
        ).hexdigest()
        return cls(
            lease_id=unsigned["lease_id"],
            decision_id=decision_id,
            subject=subject,
            issued_at=unsigned["issued_at"],
            expires_at=expires_at,
            allowed_backend=allowed_backend,
            allowed_model_id=allowed_model_id,
            maximum_hourly_usd=float(maximum_hourly_usd),
            maximum_total_usd=float(maximum_total_usd),
            maximum_attempts=int(maximum_attempts),
            fallback_allowed=bool(fallback_allowed),
            nonce=unsigned["nonce"],
            signature=signature,
        )

    def unsigned_dict(self) -> dict[str, Any]:
        value = self.as_dict()
        value.pop("signature")
        return value

    def verify(
        self,
        secret: bytes,
        *,
        now: datetime | None = None,
        subject: str | None = None,
        backend: BackendKind | None = None,
        model_id: str | None = None,
    ) -> None:
        expected = hmac.new(
            secret,
            canonical_json(self.unsigned_dict()).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, self.signature):
            raise PermissionError("approval lease signature is invalid")
        current = now or datetime.now(UTC)
        expiry = datetime.fromisoformat(self.expires_at)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if current >= expiry:
            raise PermissionError("approval lease has expired")
        if subject is not None and self.subject != subject:
            raise PermissionError("approval lease subject mismatch")
        if backend is not None and self.allowed_backend != backend:
            raise PermissionError("approval lease backend mismatch")
        if model_id is not None and self.allowed_model_id != model_id:
            raise PermissionError("approval lease model mismatch")
        if min(self.maximum_hourly_usd, self.maximum_total_usd) <= 0:
            raise PermissionError("approval lease has invalid spend ceilings")
        if self.maximum_attempts < 1:
            raise PermissionError("approval lease permits no attempts")

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ProviderResource:
    backend: BackendKind
    resource_id: str
    lifecycle: ProviderLifecycle
    model_id: str
    hourly_usd: float
    created_at: str
    last_observed_at: str
    endpoint_url: str | None = None
    storage_usd_per_hour: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ProviderError:
    code: str
    message: str
    retryable: bool
    ambiguous_mutation: bool
    terminal: bool
    provider_status: str | None = None
    retry_after_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    state: ExecutionState
    model_id: str
    backend: BackendKind
    started_at: str
    completed_at: str | None
    success: bool
    verified: bool
    actual_cost_usd: float | None
    latency_ms: float | None
    output_digest: str | None
    error: ProviderError | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _encode(self)
