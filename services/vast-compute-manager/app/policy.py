from __future__ import annotations

from dataclasses import dataclass

from .settings import Settings


class PolicyViolation(ValueError):
    """Raised when a requested allocation exceeds an enforced limit."""


@dataclass(frozen=True, slots=True)
class ApprovedRequest:
    max_hourly_usd: float
    disk_gb: int
    ttl_minutes: int
    estimated_max_cost_usd: float


def approve_request(
    *,
    settings: Settings,
    requested_max_hourly_usd: float | None,
    disk_gb: int,
    ttl_minutes: int,
    active_instances: int,
) -> ApprovedRequest:
    hourly_cap = requested_max_hourly_usd or settings.max_hourly_usd

    if active_instances >= settings.max_active_instances:
        raise PolicyViolation("maximum active instance count reached")
    if hourly_cap > settings.max_hourly_usd:
        raise PolicyViolation("requested hourly cap exceeds server policy")
    if disk_gb > settings.max_disk_gb:
        raise PolicyViolation("requested disk exceeds server policy")
    if ttl_minutes > settings.max_ttl_minutes:
        raise PolicyViolation("requested lifetime exceeds server policy")

    estimated_cost = hourly_cap * (ttl_minutes / 60)
    if estimated_cost > settings.max_total_usd:
        raise PolicyViolation("estimated job cost exceeds server policy")

    return ApprovedRequest(
        max_hourly_usd=hourly_cap,
        disk_gb=disk_gb,
        ttl_minutes=ttl_minutes,
        estimated_max_cost_usd=round(estimated_cost, 4),
    )
