from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .models import BrokerPolicy, ModelSpec, Offer


class VastError(RuntimeError):
    """Raised when Vast offer discovery fails."""


class VastOfferDiscovery:
    API_URL = "https://console.vast.ai/api/v0/bundles/"
    TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        max_attempts: int = 4,
        api_url: str | None = None,
    ):
        self.api_key = api_key or os.getenv("VAST_API_KEY")
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.api_url = api_url or os.getenv("MENTAT_VAST_BUNDLES_URL") or self.API_URL

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, payload: dict[str, Any]) -> Any:
        if not self.api_key:
            raise VastError("VAST_API_KEY is not configured")
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                self.api_url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "MentatBroker/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")[:2000]
                if exc.code not in self.TRANSIENT_HTTP_CODES or attempt == self.max_attempts:
                    raise VastError(
                        f"Vast offer search failed with HTTP {exc.code}: {details}"
                    ) from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == self.max_attempts:
                    raise VastError(f"Vast offer search failed: {exc}") from exc
            time.sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
        raise VastError("Vast offer search failed after retries")

    def search(self, model: ModelSpec, policy: BrokerPolicy, limit: int = 12) -> list[Offer]:
        if model.provider != "vast" or not self.api_key:
            return []
        hourly_cap = min(model.max_hourly_usd, policy.max_hourly_usd)
        payload: dict[str, Any] = {
            "limit": max(1, min(limit, 100)),
            "type": "ondemand",
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "rented": {"eq": False},
            "reliability": {"gte": policy.minimum_reliability},
            "num_gpus": {"eq": model.num_gpus},
            "gpu_ram": {"gte": model.min_gpu_ram_mb},
            "gpu_arch": {"eq": "nvidia"},
            "disk_space": {"gte": model.min_disk_gb},
            "duration": {"gte": int(policy.max_session_hours * 3600)},
            "dph_total": {"lte": hourly_cap},
            "order": [["dph_total", "asc"], ["reliability", "desc"]],
        }
        if model.gpu_names:
            payload["gpu_name"] = {"in": model.gpu_names}
        if model.min_nvlink_bw > 0:
            payload["bw_nvlink"] = {"gte": model.min_nvlink_bw}

        parsed = self._request(payload)
        raw_offers: Any
        if isinstance(parsed, dict):
            raw_offers = parsed.get("offers", parsed.get("results", []))
        else:
            raw_offers = parsed
        if isinstance(raw_offers, dict):
            raw_offers = [raw_offers]
        if not isinstance(raw_offers, list):
            raise VastError("Vast offer search returned an unexpected response shape")

        offers: list[Offer] = []
        for raw in raw_offers:
            try:
                offer = Offer.from_vast(dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
            if not offer.verified:
                continue
            if offer.hourly_usd <= 0 or offer.hourly_usd > hourly_cap:
                continue
            if offer.reliability < policy.minimum_reliability:
                continue
            if offer.num_gpus != model.num_gpus or offer.gpu_ram_mb < model.min_gpu_ram_mb:
                continue
            if model.gpu_names and offer.gpu_name not in model.gpu_names:
                continue
            if offer.disk_space_gb is not None and offer.disk_space_gb < model.min_disk_gb:
                continue
            if model.min_nvlink_bw > 0 and (
                offer.bw_nvlink is None or offer.bw_nvlink < model.min_nvlink_bw
            ):
                continue
            offers.append(offer)
        return sorted(offers, key=lambda item: (item.hourly_usd, -item.reliability))[:limit]
