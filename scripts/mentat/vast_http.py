from __future__ import annotations

import json
import os
import random
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://console.vast.ai/api/v0"
TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class VastApiError(RuntimeError):
    """Raised when the Vast API returns a non-successful response."""


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 90,
    attempts: int = 5,
    allow_not_found: bool = False,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "Mentat/1.0",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(1, max(1, attempts) + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            if not raw:
                return {}
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise VastApiError(f"Vast API returned a non-object response for {method} {url}")
            return parsed
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:4000]
            if allow_not_found and exc.code == 404:
                return {"not_found": True}
            transient = exc.code in TRANSIENT_HTTP_CODES
            if not transient or attempt >= attempts:
                raise VastApiError(
                    f"Vast API {exc.code} for {method} {url}: {details}"
                ) from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 0.0
            except ValueError:
                delay = 0.0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt >= attempts:
                raise VastApiError(f"Vast API connection failed for {method} {url}: {exc}") from exc
            delay = 0.0
        delay = max(delay, min(8.0, 0.5 * (2 ** (attempt - 1))))
        time.sleep(delay + random.uniform(0, 0.2))
    raise VastApiError("Vast API request failed after retries")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def result_id(payload: dict[str, Any]) -> int:
    for key in ("id", "result"):
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("id")
        if value is not None:
            return int(value)
    raise VastApiError("Vast API response did not include a resource id")


def results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw: Any = payload.get("results", payload.get("offers", []))
    if isinstance(raw, dict):
        return [dict(raw)]
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]
