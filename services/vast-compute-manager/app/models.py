from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OfferSearchRequest(BaseModel):
    gpu_name: str = Field(default="RTX_4090", min_length=1, max_length=80)
    num_gpus: int = Field(default=1, ge=1, le=8)
    max_hourly_usd: float | None = Field(default=None, gt=0)
    limit: int = Field(default=5, ge=1, le=20)


class Offer(BaseModel):
    id: int
    gpu_name: str | None = None
    num_gpus: int | None = None
    gpu_ram_mb: int | None = None
    hourly_usd: float
    reliability: float | None = None
    verified: bool | None = None
    raw: dict[str, Any] | None = None


class InstanceCreateRequest(BaseModel):
    offer_id: int = Field(gt=0)
    profile: str = Field(default="pytorch", pattern=r"^[a-z0-9_-]+$")
    disk_gb: int = Field(default=40, ge=20)
    ttl_minutes: int = Field(default=15, ge=1)
    max_hourly_usd: float | None = Field(default=None, gt=0)


class InstanceSummary(BaseModel):
    instance_id: int
    status: str | None = None
    hourly_usd: float | None = None
    expires_at: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
