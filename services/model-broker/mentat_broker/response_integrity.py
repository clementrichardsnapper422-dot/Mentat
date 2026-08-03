from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Any

from .models import BenchmarkRecord, Decision, ModelSpec
from .sessions import SessionError
from .store import utc_now

MAX_JSON_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_BYTES = 2 * 1024 * 1024


def _validate_tool_calls(tool_calls: list[Any]) -> None:
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            raise SessionError("upstream assistant tool call is invalid")
        if not isinstance(tool_call.get("id"), str) or not tool_call["id"].strip():
            raise SessionError("upstream assistant tool call did not contain an id")
        if tool_call.get("type") != "function":
            raise SessionError("upstream assistant tool call type is unsupported")
        function = tool_call.get("function")
        if not isinstance(function, dict):
            raise SessionError("upstream assistant tool call did not contain a function")
        if not isinstance(function.get("name"), str) or not function["name"].strip():
            raise SessionError("upstream assistant tool call did not contain a function name")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise SessionError("upstream assistant tool call arguments must be JSON text")
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise SessionError(
                "upstream assistant tool call arguments were malformed JSON"
            ) from exc
        if not isinstance(parsed_arguments, dict):
            raise SessionError("upstream assistant tool call arguments must be a JSON object")


def _completion_tokens(usage: Any) -> float | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get("completion_tokens")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    tokens = float(value)
    if not math.isfinite(tokens) or tokens <= 0:
        return None
    return tokens


def _validate_json_completion(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("upstream returned malformed completion JSON") from exc
    if not isinstance(parsed, dict):
        raise SessionError("upstream completion must be a JSON object")
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SessionError("upstream completion did not contain any choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise SessionError("upstream completion choice is invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise SessionError("upstream completion did not contain an assistant message")
    has_content = isinstance(message.get("content"), str) and bool(message["content"])
    tool_calls = message.get("tool_calls")
    has_tools = isinstance(tool_calls, list) and bool(tool_calls)
    if tool_calls is not None and not isinstance(tool_calls, list):
        raise SessionError("upstream assistant tool calls must be a list")
    if has_tools:
        _validate_tool_calls(tool_calls)
    if not has_content and not has_tools:
        raise SessionError("upstream assistant message contained neither content nor tool calls")
    return parsed


def _record_failure(
    application: Any, model: ModelSpec, decision: Decision, started: float, error: str
) -> None:
    latency_ms = (time.monotonic() - started) * 1000
    application.store.update_decision_status(
        decision.id,
        "failed",
        error=error,
        completed_at=utc_now(),
    )
    application.store.add_benchmark(
        BenchmarkRecord(
            model_id=model.id,
            task_class=decision.task_class,
            success=False,
            latency_ms=latency_ms,
            tokens_per_second=None,
            hourly_usd=decision.offer.hourly_usd if decision.offer else None,
            total_cost_usd=decision.estimated_cost_usd,
            quality_score=None,
            notes=f"Automatic failed runtime measurement for decision {decision.id}: {error}",
        )
    )


def hardened_proxy_to_model(
    application: Any,
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    model: ModelSpec,
    base_url: str,
    decision: Decision,
    started: float,
) -> None:
    upstream_payload = dict(payload)
    for key in list(upstream_payload):
        if key.startswith("mentat_"):
            upstream_payload.pop(key, None)
    upstream_payload["model"] = model.model_id
    body = json.dumps(upstream_payload).encode("utf-8")
    api_key = os.getenv(model.api_key_env) or os.getenv("VAST_API_KEY") or "EMPTY"
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        },
    )
    try:
        response = urllib.request.urlopen(
            request,
            timeout=application.registry.policy.endpoint_ready_timeout_seconds,
        )
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            details = exc.read().decode("utf-8", errors="replace")
            raise SessionError(
                f"upstream rejected the request with HTTP {exc.code}: {details}"
            ) from exc
        raise

    content_type = response.headers.get("Content-Type", "application/json")
    tokens_per_second = None
    captured = bytearray()

    try:
        if "application/json" in content_type:
            raw = response.read(MAX_JSON_RESPONSE_BYTES + 1)
            if len(raw) > MAX_JSON_RESPONSE_BYTES:
                raise SessionError("upstream JSON completion exceeded the response-size limit")
            parsed = _validate_json_completion(raw)
            latency_ms = (time.monotonic() - started) * 1000
            completion_tokens = _completion_tokens(parsed.get("usage"))
            if completion_tokens is not None and latency_ms > 0:
                tokens_per_second = completion_tokens / (latency_ms / 1000)
            handler.send_response(response.status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("X-Mentat-Decision-Id", decision.id)
            handler.send_header("X-Mentat-Model", model.id)
            handler.send_header("Connection", "close")
            handler.end_headers()
            # Keep completion connection-delimited so clients cannot finish before
            # the decision and runtime evidence below have been durably recorded.
            handler.wfile.write(raw)
            handler.wfile.flush()
        elif "text/event-stream" in content_type:
            handler.send_response(response.status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("X-Mentat-Decision-Id", decision.id)
            handler.send_header("X-Mentat-Model", model.id)
            handler.send_header("Connection", "close")
            handler.end_headers()
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handler.wfile.write(chunk)
                handler.wfile.flush()
                if len(captured) < MAX_CAPTURE_BYTES:
                    captured.extend(chunk[: MAX_CAPTURE_BYTES - len(captured)])
            if b"data: [DONE]" not in captured:
                raise SessionError("upstream stream ended without an OpenAI [DONE] terminator")
            latency_ms = (time.monotonic() - started) * 1000
        else:
            raise SessionError(f"unsupported upstream content type: {content_type}")
    except SessionError as exc:
        _record_failure(application, model, decision, started, str(exc))
        raise
    finally:
        response.close()

    application.sessions.touch(model.id)
    application.store.update_decision_status(
        decision.id,
        "completed",
        completed_at=utc_now(),
    )
    application.store.add_benchmark(
        BenchmarkRecord(
            model_id=model.id,
            task_class=decision.task_class,
            success=True,
            latency_ms=latency_ms,
            tokens_per_second=tokens_per_second,
            hourly_usd=decision.offer.hourly_usd if decision.offer else None,
            total_cost_usd=decision.estimated_cost_usd,
            quality_score=None,
            notes=f"Automatic runtime measurement for decision {decision.id}",
        )
    )
