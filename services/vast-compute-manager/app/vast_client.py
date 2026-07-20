from __future__ import annotations

from typing import Any

from vastai import VastAI


APPROVED_PROFILES: dict[str, dict[str, Any]] = {
    "pytorch": {
        "image": "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
        "onstart_cmd": "nvidia-smi",
    },
}


class VastClient:
    def __init__(self, api_key: str) -> None:
        self._client = VastAI(api_key=api_key)

    def search_offers(
        self,
        *,
        gpu_name: str,
        num_gpus: int,
        max_hourly_usd: float,
        limit: int,
    ) -> list[dict[str, Any]]:
        query = (
            f"gpu_name={gpu_name} num_gpus={num_gpus} verified=true "
            "direct_port_count>=1 rentable=true"
        )
        raw = self._client.search_offers(query=query, order="dlperf_usd-", limit=str(limit))
        return [
            offer
            for offer in raw
            if float(offer.get("dph_total", float("inf"))) <= max_hourly_usd
        ]

    def get_offer(self, offer_id: int) -> dict[str, Any] | None:
        offers = self._client.search_offers(
            query=f"id={offer_id} verified=true rentable=true",
            limit="1",
        )
        return offers[0] if offers else None

    def create_instance(self, *, offer_id: int, profile: str, disk_gb: int) -> int:
        config = APPROVED_PROFILES[profile]
        result = self._client.create_instance(
            id=offer_id,
            image=config["image"],
            disk=disk_gb,
            onstart_cmd=config["onstart_cmd"],
            ssh=True,
            direct=True,
        )
        instance_id = result.get("new_contract")
        if not instance_id:
            raise RuntimeError(f"Vast did not return an instance id: {result}")
        return int(instance_id)

    def show_instance(self, instance_id: int) -> dict[str, Any]:
        return self._client.show_instance(id=instance_id)

    def destroy_instance(self, instance_id: int) -> Any:
        return self._client.destroy_instance(id=instance_id)
