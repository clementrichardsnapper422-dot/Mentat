"""Stable provider-neutral compute backend boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .contracts import (
    ApprovalLease,
    BackendKind,
    ExecutionCandidate,
    ProviderError,
    ProviderLifecycle,
    ProviderResource,
    utc_now,
)


class BackendError(RuntimeError):
    def __init__(self, error: ProviderError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class BackendCapabilities:
    kind: BackendKind
    production_eligible: bool
    can_acquire: bool
    can_reuse: bool
    can_cool: bool
    can_stop: bool
    can_destroy: bool
    supports_idempotency_key: bool
    billing_source: str

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "kind": self.kind.value}


@runtime_checkable
class ComputeBackend(Protocol):
    @property
    def capabilities(self) -> BackendCapabilities: ...

    def acquire(
        self,
        candidate: ExecutionCandidate,
        lease: ApprovalLease,
        *,
        idempotency_key: str,
    ) -> ProviderResource: ...

    def observe(self, resource_id: str) -> ProviderResource: ...

    def cool(self, resource_id: str) -> ProviderResource: ...

    def destroy(self, resource_id: str) -> ProviderResource: ...

    def reconcile_create(self, idempotency_key: str) -> ProviderResource | None: ...

    def billing(self, resource_id: str) -> dict[str, Any]: ...


class BackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[BackendKind, ComputeBackend] = {}

    def register(self, backend: ComputeBackend) -> None:
        kind = backend.capabilities.kind
        if kind in self._backends:
            raise ValueError(f"backend already registered: {kind.value}")
        self._backends[kind] = backend

    def get(self, kind: BackendKind, *, require_production: bool = True) -> ComputeBackend:
        backend = self._backends.get(kind)
        if backend is None:
            raise KeyError(f"backend is not registered: {kind.value}")
        if require_production and not backend.capabilities.production_eligible:
            raise BackendError(
                ProviderError(
                    code="backend_not_production_eligible",
                    message=f"{kind.value} has not passed its production gates",
                    retryable=False,
                    ambiguous_mutation=False,
                    terminal=True,
                )
            )
        return backend

    def describe(self) -> list[dict[str, Any]]:
        return [
            self._backends[kind].capabilities.as_dict()
            for kind in sorted(self._backends, key=lambda value: value.value)
        ]


class GuardedServerlessBackend:
    """Adapter around validated Vast Serverless lifecycle functions."""

    def __init__(
        self,
        *,
        acquire_fn: Callable[[ExecutionCandidate, ApprovalLease, str], dict[str, Any]],
        observe_fn: Callable[[str], dict[str, Any]],
        cool_fn: Callable[[str], dict[str, Any]],
        billing_fn: Callable[[str], dict[str, Any]],
        reconcile_fn: Callable[[str], dict[str, Any] | None] | None = None,
        destroy_fn: Callable[[str], dict[str, Any]] | None = None,
        production_eligible: bool = False,
    ) -> None:
        self._acquire_fn = acquire_fn
        self._observe_fn = observe_fn
        self._cool_fn = cool_fn
        self._billing_fn = billing_fn
        self._reconcile_fn = reconcile_fn
        self._destroy_fn = destroy_fn
        self._capabilities = BackendCapabilities(
            kind=BackendKind.VAST_SERVERLESS,
            production_eligible=production_eligible,
            can_acquire=True,
            can_reuse=True,
            can_cool=True,
            can_stop=False,
            can_destroy=destroy_fn is not None,
            supports_idempotency_key=reconcile_fn is not None,
            billing_source="vast",
        )

    @property
    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    def acquire(
        self,
        candidate: ExecutionCandidate,
        lease: ApprovalLease,
        *,
        idempotency_key: str,
    ) -> ProviderResource:
        if not candidate.eligible:
            raise self._error("candidate_ineligible", "cannot acquire an ineligible candidate")
        if candidate.profile.backend != BackendKind.VAST_SERVERLESS:
            raise self._error("backend_mismatch", "candidate backend does not match Serverless")
        if candidate.market is None:
            raise self._error("missing_live_offer", "Serverless acquisition requires a fresh offer")
        if candidate.market.hourly_usd > lease.maximum_hourly_usd:
            raise self._error("price_ceiling_exceeded", "offer exceeds approved hourly ceiling")
        try:
            return self._normalize(self._acquire_fn(candidate, lease, idempotency_key))
        except TimeoutError as exc:
            raise BackendError(
                ProviderError(
                    code="create_outcome_ambiguous",
                    message=str(exc) or "Serverless acquisition timed out",
                    retryable=False,
                    ambiguous_mutation=True,
                    terminal=False,
                    metadata={"idempotency_key": idempotency_key},
                )
            ) from exc
        except BackendError:
            raise
        except Exception as exc:
            raise self._error("serverless_acquire_failed", str(exc)) from exc

    def observe(self, resource_id: str) -> ProviderResource:
        return self._resource_call(self._observe_fn, resource_id, "observe")

    def cool(self, resource_id: str) -> ProviderResource:
        return self._resource_call(self._cool_fn, resource_id, "cool")

    def destroy(self, resource_id: str) -> ProviderResource:
        if self._destroy_fn is None:
            raise self._error("destroy_unsupported", "Serverless destroy is not validated")
        return self._resource_call(self._destroy_fn, resource_id, "destroy")

    def reconcile_create(self, idempotency_key: str) -> ProviderResource | None:
        if self._reconcile_fn is None:
            raise self._error(
                "create_reconciliation_unsupported",
                "create cannot be retried until exact remote absence is proven",
            )
        raw = self._reconcile_fn(idempotency_key)
        return self._normalize(raw) if raw else None

    def billing(self, resource_id: str) -> dict[str, Any]:
        try:
            value = self._billing_fn(resource_id)
        except Exception as exc:
            raise self._error("billing_read_failed", str(exc), retryable=True) from exc
        if not isinstance(value, dict) or value.get("actual_usd") is None:
            raise self._error("billing_shape_invalid", "billing omitted actual_usd")
        actual = float(value["actual_usd"])
        if actual < 0:
            raise self._error("billing_value_invalid", "billing cannot be negative")
        return {**value, "actual_usd": actual, "source": value.get("source", "vast")}

    def _resource_call(
        self,
        action: Callable[[str], dict[str, Any]],
        resource_id: str,
        operation: str,
    ) -> ProviderResource:
        if not resource_id:
            raise ValueError("resource id is required")
        try:
            return self._normalize(action(resource_id))
        except TimeoutError as exc:
            raise BackendError(
                ProviderError(
                    code=f"{operation}_outcome_ambiguous",
                    message=str(exc) or f"{operation} timed out",
                    retryable=False,
                    ambiguous_mutation=True,
                    terminal=False,
                    metadata={"resource_id": resource_id},
                )
            ) from exc
        except BackendError:
            raise
        except Exception as exc:
            raise self._error(f"{operation}_failed", str(exc), retryable=True) from exc

    @staticmethod
    def _error(code: str, message: str, *, retryable: bool = False) -> BackendError:
        return BackendError(
            ProviderError(
                code=code,
                message=message,
                retryable=retryable,
                ambiguous_mutation=False,
                terminal=not retryable,
            )
        )

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> ProviderResource:
        if not isinstance(raw, dict):
            raise GuardedServerlessBackend._error(
                "provider_shape_invalid", "provider resource must be an object"
            )
        resource_id = str(raw.get("resource_id") or raw.get("id") or "").strip()
        if not resource_id:
            raise GuardedServerlessBackend._error(
                "provider_identity_missing", "provider omitted resource identity"
            )
        status = str(raw.get("lifecycle") or raw.get("status") or "unknown").lower()
        aliases = {
            "running": ProviderLifecycle.READY,
            "active": ProviderLifecycle.READY,
            "idle": ProviderLifecycle.READY,
            "cold": ProviderLifecycle.COOLED,
            "deleted": ProviderLifecycle.DESTROYED,
            "error": ProviderLifecycle.FAILED,
        }
        try:
            lifecycle = ProviderLifecycle(status)
        except ValueError:
            lifecycle = aliases.get(status, ProviderLifecycle.UNKNOWN)
        hourly = float(raw.get("hourly_usd") or raw.get("rate_usd") or 0)
        if hourly < 0:
            raise GuardedServerlessBackend._error(
                "provider_rate_invalid", "provider hourly rate cannot be negative"
            )
        return ProviderResource(
            backend=BackendKind.VAST_SERVERLESS,
            resource_id=resource_id,
            lifecycle=lifecycle,
            model_id=str(raw.get("model_id") or "unknown"),
            hourly_usd=hourly,
            created_at=str(raw.get("created_at") or utc_now()),
            last_observed_at=str(raw.get("last_observed_at") or utc_now()),
            endpoint_url=str(raw["endpoint_url"]) if raw.get("endpoint_url") else None,
            storage_usd_per_hour=(
                float(raw["storage_usd_per_hour"])
                if raw.get("storage_usd_per_hour") is not None
                else None
            ),
            metadata={"raw_status": status},
        )


class ExperimentalDirectBackend:
    """Explicit stop sign for deferred direct-instance work."""

    capabilities = BackendCapabilities(
        kind=BackendKind.VAST_DIRECT,
        production_eligible=False,
        can_acquire=False,
        can_reuse=False,
        can_cool=False,
        can_stop=False,
        can_destroy=False,
        supports_idempotency_key=False,
        billing_source="unvalidated",
    )

    @staticmethod
    def _disabled() -> BackendError:
        return BackendError(
            ProviderError(
                code="direct_backend_not_validated",
                message=(
                    "Vast direct instances are experimental and outside the frozen "
                    "Mentat 1.0 release path"
                ),
                retryable=False,
                ambiguous_mutation=False,
                terminal=True,
            )
        )

    def acquire(
        self,
        candidate: ExecutionCandidate,
        lease: ApprovalLease,
        *,
        idempotency_key: str,
    ) -> ProviderResource:
        raise self._disabled()

    def observe(self, resource_id: str) -> ProviderResource:
        raise self._disabled()

    def cool(self, resource_id: str) -> ProviderResource:
        raise self._disabled()

    def destroy(self, resource_id: str) -> ProviderResource:
        raise self._disabled()

    def reconcile_create(self, idempotency_key: str) -> ProviderResource | None:
        raise self._disabled()

    def billing(self, resource_id: str) -> dict[str, Any]:
        raise self._disabled()


class FakeBackend:
    """Deterministic zero-dollar backend for acceptance tests."""

    capabilities = BackendCapabilities(
        kind=BackendKind.FAKE,
        production_eligible=True,
        can_acquire=True,
        can_reuse=True,
        can_cool=True,
        can_stop=True,
        can_destroy=True,
        supports_idempotency_key=True,
        billing_source="fake-zero-dollar",
    )

    def __init__(self) -> None:
        self._resources: dict[str, ProviderResource] = {}
        self._keys: dict[str, str] = {}

    def acquire(
        self,
        candidate: ExecutionCandidate,
        lease: ApprovalLease,
        *,
        idempotency_key: str,
    ) -> ProviderResource:
        existing = self.reconcile_create(idempotency_key)
        if existing:
            return existing
        resource_id = f"fake-{len(self._resources) + 1}"
        resource = ProviderResource(
            backend=BackendKind.FAKE,
            resource_id=resource_id,
            lifecycle=ProviderLifecycle.READY,
            model_id=candidate.profile.model_id,
            hourly_usd=0,
            created_at=utc_now(),
            last_observed_at=utc_now(),
            endpoint_url=f"http://127.0.0.1/{resource_id}",
            metadata={"paid_compute_used": False, "lease_id": lease.lease_id},
        )
        self._resources[resource_id] = resource
        self._keys[idempotency_key] = resource_id
        return resource

    def observe(self, resource_id: str) -> ProviderResource:
        try:
            return self._resources[resource_id]
        except KeyError as exc:
            raise BackendError(
                ProviderError(
                    code="resource_not_found",
                    message="fake resource not found",
                    retryable=False,
                    ambiguous_mutation=False,
                    terminal=True,
                )
            ) from exc

    def cool(self, resource_id: str) -> ProviderResource:
        return self._replace(resource_id, ProviderLifecycle.COOLED)

    def destroy(self, resource_id: str) -> ProviderResource:
        return self._replace(resource_id, ProviderLifecycle.DESTROYED)

    def reconcile_create(self, idempotency_key: str) -> ProviderResource | None:
        resource_id = self._keys.get(idempotency_key)
        return self._resources.get(resource_id) if resource_id else None

    def billing(self, resource_id: str) -> dict[str, Any]:
        self.observe(resource_id)
        return {"actual_usd": 0.0, "source": "fake-zero-dollar"}

    def _replace(
        self,
        resource_id: str,
        lifecycle: ProviderLifecycle,
    ) -> ProviderResource:
        current = self.observe(resource_id)
        updated = ProviderResource(
            backend=current.backend,
            resource_id=current.resource_id,
            lifecycle=lifecycle,
            model_id=current.model_id,
            hourly_usd=current.hourly_usd,
            created_at=current.created_at,
            last_observed_at=utc_now(),
            endpoint_url=current.endpoint_url,
            storage_usd_per_hour=current.storage_usd_per_hour,
            metadata=current.metadata,
        )
        self._resources[resource_id] = updated
        return updated
