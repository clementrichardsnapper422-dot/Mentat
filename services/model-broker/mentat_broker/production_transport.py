from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .models import ModelSpec
from .production_sessions import ProductionSessionManager as BaseProductionSessionManager
from .sessions import SessionError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_loopback_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in LOOPBACK_HOSTS


def validate_upstream_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SessionError("upstream endpoint must be an absolute HTTP or HTTPS URL")
    if parsed.scheme != "https" and parsed.hostname not in LOOPBACK_HOSTS:
        raise SessionError("non-loopback upstream endpoints must use HTTPS")


def open_upstream(
    request: urllib.request.Request,
    *,
    timeout: float,
):
    """Open an upstream request without leaking local traffic through a proxy.

    Vast endpoints must use HTTPS. Plain HTTP is allowed only for loopback
    integration endpoints. Loopback calls use an opener with no proxy handlers
    so Windows system proxy settings cannot delay or intercept local traffic.
    """

    validate_upstream_url(request.full_url)
    if is_loopback_url(request.full_url):
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return direct.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


class ProductionSessionManager(BaseProductionSessionManager):
    """Production lifecycle manager with proxy-safe readiness behavior."""

    def wait_until_ready(self, model: ModelSpec, timeout_seconds: int | None = None) -> str:
        endpoint_url = self.endpoint_url(model)
        if not endpoint_url:
            raise SessionError(f"no endpoint URL is configured for {model.id}")
        validate_upstream_url(endpoint_url)
        if not self.is_approved(model.id):
            raise SessionError(f"no approved session is active for {model.display_name}")
        if not self.registry.policy.maintain_warm_worker:
            # In zero-floor Serverless mode the real task request is the wake-up
            # request. A throwaway model inference here would add cost, latency,
            # and a second failure point before the user's task even starts.
            return endpoint_url
        return super().wait_until_ready(model, timeout_seconds)

    def _probe(self, base_url: str) -> bool:
        model = getattr(self._thread_state, "probe_model", None)
        if not isinstance(model, ModelSpec):
            return False
        api_key = os.getenv("VAST_API_KEY") or "EMPTY"
        payload = json.dumps(
            {
                "model": model.model_id,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "MentatBroker/1.0",
            },
        )
        try:
            with open_upstream(request, timeout=15) as response:
                response.read(4096)
                return 200 <= response.status < 300
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return False
