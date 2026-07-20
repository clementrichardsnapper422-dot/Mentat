from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .models import InstanceCreateRequest, InstanceSummary, Offer, OfferSearchRequest
from .policy import PolicyViolation, approve_request
from .settings import Settings
from .vast_client import APPROVED_PROFILES, VastClient

app = FastAPI(title="Mentat Vast Compute Manager", version="0.1.0")
settings = Settings.from_env()
_allocations: dict[int, datetime] = {}


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if settings.manager_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MENTAT_COMPUTE_TOKEN is not configured",
        )
    if authorization != f"Bearer {settings.manager_token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def get_client() -> VastClient:
    if not settings.vast_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAST_API_KEY is not configured",
        )
    return VastClient(settings.vast_api_key)


def _offer(raw: dict) -> Offer:
    return Offer(
        id=int(raw["id"]),
        gpu_name=raw.get("gpu_name"),
        num_gpus=raw.get("num_gpus"),
        gpu_ram_mb=raw.get("gpu_ram"),
        hourly_usd=float(raw["dph_total"]),
        reliability=raw.get("reliability2"),
        verified=raw.get("verified"),
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "vast_configured": bool(settings.vast_api_key),
        "auth_configured": bool(settings.manager_token),
        "approved_profiles": sorted(APPROVED_PROFILES),
    }


@app.post("/v1/offers/search", dependencies=[Depends(require_token)])
def search_offers(request: OfferSearchRequest) -> dict[str, list[Offer]]:
    hourly_cap = min(request.max_hourly_usd or settings.max_hourly_usd, settings.max_hourly_usd)
    raw = get_client().search_offers(
        gpu_name=request.gpu_name,
        num_gpus=request.num_gpus,
        max_hourly_usd=hourly_cap,
        limit=request.limit,
    )
    return {"offers": [_offer(item) for item in raw]}


@app.post("/v1/instances", dependencies=[Depends(require_token)])
def create_instance(request: InstanceCreateRequest) -> InstanceSummary:
    try:
        approved = approve_request(
            settings=settings,
            requested_max_hourly_usd=request.max_hourly_usd,
            disk_gb=request.disk_gb,
            ttl_minutes=request.ttl_minutes,
            active_instances=len(_allocations),
        )
    except PolicyViolation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if request.profile not in APPROVED_PROFILES:
        raise HTTPException(status_code=400, detail="unapproved workload profile")

    client = get_client()
    offer = client.get_offer(request.offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer is unavailable")

    actual_hourly = float(offer.get("dph_total", float("inf")))
    if actual_hourly > approved.max_hourly_usd:
        raise HTTPException(status_code=400, detail="offer price exceeds approved hourly cap")

    instance_id = client.create_instance(
        offer_id=request.offer_id,
        profile=request.profile,
        disk_gb=approved.disk_gb,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=approved.ttl_minutes)
    _allocations[instance_id] = expires_at
    return InstanceSummary(
        instance_id=instance_id,
        status="created",
        hourly_usd=actual_hourly,
        expires_at=expires_at.isoformat(),
    )


@app.get("/v1/instances/{instance_id}", dependencies=[Depends(require_token)])
def show_instance(instance_id: int) -> InstanceSummary:
    info = get_client().show_instance(instance_id)
    expires_at = _allocations.get(instance_id)
    return InstanceSummary(
        instance_id=instance_id,
        status=info.get("actual_status"),
        hourly_usd=info.get("dph_total"),
        expires_at=expires_at.isoformat() if expires_at else None,
        ssh_host=info.get("ssh_host"),
        ssh_port=info.get("ssh_port"),
    )


@app.delete("/v1/instances/{instance_id}", dependencies=[Depends(require_token)])
def destroy_instance(instance_id: int) -> dict[str, object]:
    result = get_client().destroy_instance(instance_id)
    _allocations.pop(instance_id, None)
    return {"instance_id": instance_id, "destroyed": True, "provider_result": result}
