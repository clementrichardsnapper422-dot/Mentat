from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import BrokerPolicy, ModelSpec, Offer


class VastError(RuntimeError):
    """Raised when Vast offer discovery fails."""


class VastOfferDiscovery:
    API_URL = "https://console.vast.ai/api/v0/bundles/"

    def __init__(self, api_key: str | None = None, timeout: int = 30):
        self.api_key = api_key or os.getenv("VAST_API_KEY")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, model: ModelSpec, policy: BrokerPolicy, limit: int = 12) -> list[Offer]:
        if model.provider != "vast" or not self.api_key:
            return []
        hourly_cap = min(model.max_hourly_usd, policy.max_hourly_usd)
        payload: dict[str, Any] = {
            "limit": max(1, min(limit, 100)),
            "type": "on-demand",
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "rented": {"eq": False},
            "reliability2": {"gte": policy.minimum_reliability},
            "num_gpus": {"eq": model.num_gpus},
            "gpu_ram": {"gte": model.min_gpu_ram_mb},
            "dph_total": {"lte": hourly_cap},
            "order": [["dph_total", "asc"]],
        }
        if model.gpu_names:
            payload["gpu_name"] = {"in": model.gpu_names}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise VastError(f"Vast offer search failed with HTTP {exc.code}: {details}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VastError(f"Vast offer search failed: {exc}") from exc

        raw_offers = parsed.get("offers", []) if isinstance(parsed, dict) else []
        if isinstance(raw_offers, dict):
            raw_offers = [raw_offers]
        offers = []
        for raw in raw_offers:
            try:
                offer = Offer.from_vast(dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
            if offer.hourly_usd <= hourly_cap and offer.reliability >= policy.minimum_reliability:
                offers.append(offer)
        return sorted(offers, key=lambda item: (item.hourly_usd, -item.reliability))[:limit]
