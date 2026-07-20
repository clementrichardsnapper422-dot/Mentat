from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .models import ModelSpec
from .production_sessions import ProductionSessionManager as BaseProductionSessionManager

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_loopback_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.hostname in LOOPBACK_HOSTS


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

    parsed = urllib.parse.urlparse(request.full_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported upstream URL scheme: {parsed.scheme or 'missing'}")
    loopback = parsed.hostname in LOOPBACK_HOSTS
    if parsed.scheme != "https" and not loopback:
        raise ValueError("non-loopback upstream endpoints must use HTTPS")
    if loopback:
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return direct.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


class ProductionSessionManager(BaseProductionSessionManager):
    """Production lifecycle manager with proxy-safe readiness probes."""

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
