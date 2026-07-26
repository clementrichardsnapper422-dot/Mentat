from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class FakeOpenAIState:
    requests: list[dict[str, Any]] = field(default_factory=list)
    active_requests: int = 0
    cancelled_requests: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, payload: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append(payload)


def _message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
    return "\n".join(parts)


def _directive(text: str, name: str) -> bool:
    return f"[[{name}]]" in text


def _delay_seconds(text: str) -> float:
    match = re.search(r"\[\[delay=(\d+(?:\.\d+)?)\]\]", text)
    return min(30.0, float(match.group(1))) if match else 0.0


def _json_completion(payload: dict[str, Any], text: str) -> dict[str, Any]:
    model = str(payload.get("model") or "fake-model")
    if _directive(text, "tool"):
        tools = payload.get("tools") or []
        function_name = "fake_tool"
        if tools and isinstance(tools[0], dict):
            function = tools[0].get("function")
            if isinstance(function, dict) and function.get("name"):
                function_name = str(function["name"])
        message: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_fake_1",
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "arguments": json.dumps({"value": "from-fake-openai"}),
                    },
                }
            ],
        }
        finish_reason = "tool_calls"
    else:
        content = "OK" if int(payload.get("max_tokens") or 0) == 1 else "Mentat no-spend inference online"
        message = {"role": "assistant", "content": content}
        finish_reason = "stop"
    completion = {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 4,
            "total_tokens": 16,
        },
    }
    if _directive(text, "malformed_tool"):
        completion["choices"][0]["message"] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [None],
        }
        completion["choices"][0]["finish_reason"] = "tool_calls"
    if _directive(text, "invalid_usage"):
        completion["usage"]["completion_tokens"] = "not-a-number"
    return completion


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    server: FakeOpenAIServer

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            self._write_json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [{"id": "fake-model", "object": "model", "owned_by": "mentat-test"}],
                },
            )
            return
        if self.path.rstrip("/") == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "fake-openai"})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            return
        if self.headers.get("Authorization") != "Bearer test-vast-key":
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "invalid test token"}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
        except (ValueError, json.JSONDecodeError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)}})
            return

        self.server.state.record(payload)
        text = _message_text(payload)
        if _directive(text, "context_error"):
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": {
                        "message": "maximum context length exceeded",
                        "type": "context_length_exceeded",
                    }
                },
            )
            return
        if _directive(text, "server_error"):
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": {"message": "simulated upstream outage", "type": "server_error"}},
            )
            return
        if _directive(text, "malformed"):
            body = b"{not-json"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        delay = _delay_seconds(text)
        with self.server.state.lock:
            self.server.state.active_requests += 1
        try:
            if delay:
                time.sleep(delay)
            if bool(payload.get("stream")) or _directive(text, "stream"):
                self._stream(payload, text)
            else:
                self._write_json(HTTPStatus.OK, _json_completion(payload, text))
        except (BrokenPipeError, ConnectionResetError):
            with self.server.state.lock:
                self.server.state.cancelled_requests += 1
        finally:
            with self.server.state.lock:
                self.server.state.active_requests -= 1

    def _stream(self, payload: dict[str, Any], text: str) -> None:
        model = str(payload.get("model") or "fake-model")
        completion_id = "chatcmpl-" + uuid.uuid4().hex
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        if _directive(text, "tool"):
            chunks = [
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_fake_1",
                                        "type": "function",
                                        "function": {"name": "fake_tool", "arguments": ""},
                                    }
                                ],
                            },
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": '{"value":"from-fake-openai"}'},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                },
            ]
        else:
            chunks = []
            for token in ("Mentat", " no-spend", " inference", " online"):
                chunks.append(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": token},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            chunks.append(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )

        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode("utf-8") + b"\n\n")
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class FakeOpenAIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int]):
        self.state = FakeOpenAIState()
        super().__init__(server_address, FakeOpenAIHandler)


def start_fake_openai() -> tuple[FakeOpenAIServer, threading.Thread]:
    server = FakeOpenAIServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
