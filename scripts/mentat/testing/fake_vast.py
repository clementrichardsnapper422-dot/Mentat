#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


@dataclass
class FakeVastState:
    api_key: str = "test-vast-key"
    next_endpoint_id: int = 1000
    next_workergroup_id: int = 2000
    endpoints: dict[int, dict[str, Any]] = field(default_factory=dict)
    workergroups: dict[int, dict[str, Any]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    billed_usd: float = 0.0
    offers: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "id": 501,
                "gpu_name": "H200",
                "num_gpus": 8,
                "gpu_ram": 141000,
                "dph_total": 24.0,
                "reliability2": 0.995,
                "verified": True,
                "rentable": True,
                "rented": False,
                "gpu_arch": "nvidia",
                "bw_nvlink": 900,
                "disk_space": 1000,
                "duration": 28800,
                "geolocation": "test-region",
                "dlperf": 100,
            },
            {
                "id": 502,
                "gpu_name": "H200",
                "num_gpus": 8,
                "gpu_ram": 141000,
                "dph_total": 29.0,
                "reliability2": 0.999,
                "verified": True,
                "rentable": True,
                "rented": False,
                "gpu_arch": "nvidia",
                "bw_nvlink": 900,
                "disk_space": 1000,
                "duration": 28800,
                "geolocation": "test-region-2",
                "dlperf": 110,
            },
        ]
    )

    def snapshot(self) -> dict[str, Any]:
        return {
            "endpoints": list(self.endpoints.values()),
            "workergroups": list(self.workergroups.values()),
            "calls": list(self.calls),
            "billed_usd": self.billed_usd,
            "offers": list(self.offers),
        }


class FakeVastServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        state: FakeVastState | None = None,
    ) -> None:
        self.state = state or FakeVastState()
        super().__init__(server_address, FakeVastHandler)


class FakeVastHandler(BaseHTTPRequestHandler):
    server: FakeVastServer
    server_version = "MentatFakeVast"
    sys_version = ""

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.server.state.api_key}"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _write_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _record(self, payload: dict[str, Any] | None = None) -> None:
        self.server.state.calls.append(
            {
                "method": self.command,
                "path": self.path,
                "payload": payload,
            }
        )

    def _resource_id(self, prefix: str) -> int | None:
        parts = self.path.rstrip("/").split("/")
        try:
            index = parts.index(prefix)
            return int(parts[index + 1])
        except (ValueError, IndexError):
            return None

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid API key"})
            return
        self._record()
        if self.path.rstrip("/") == "/api/v0/endptjobs":
            self._write_json(
                HTTPStatus.OK,
                {"results": list(self.server.state.endpoints.values())},
            )
            return
        if self.path.rstrip("/") == "/api/v0/workergroups":
            self._write_json(
                HTTPStatus.OK,
                {"results": list(self.server.state.workergroups.values())},
            )
            return
        if self.path.rstrip("/") == "/api/v0/billing":
            self._write_json(
                HTTPStatus.OK,
                {
                    "results": [
                        {
                            "provider": "fake-vast",
                            "total_usd": self.server.state.billed_usd,
                        }
                    ]
                },
            )
            return
        if self.path.rstrip("/") == "/__state":
            self._write_json(HTTPStatus.OK, self.server.state.snapshot())
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid API key"})
            return
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._record(payload)
        if self.path.rstrip("/") == "/api/v0/bundles":
            self._write_json(HTTPStatus.OK, {"offers": self.server.state.offers})
            return
        if self.path.rstrip("/") == "/api/v0/endptjobs":
            resource_id = self.server.state.next_endpoint_id
            self.server.state.next_endpoint_id += 1
            resource = {"id": resource_id, **payload}
            self.server.state.endpoints[resource_id] = resource
            self._write_json(HTTPStatus.CREATED, {"result": resource_id})
            return
        if self.path.rstrip("/") == "/api/v0/workergroups":
            endpoint_id = int(payload.get("endpoint_id") or 0)
            if endpoint_id not in self.server.state.endpoints:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "unknown endpoint"})
                return
            resource_id = self.server.state.next_workergroup_id
            self.server.state.next_workergroup_id += 1
            resource = {"id": resource_id, **payload}
            self.server.state.workergroups[resource_id] = resource
            self._write_json(HTTPStatus.CREATED, {"result": resource_id})
            return
        if self.path.rstrip("/") == "/__reset":
            api_key = self.server.state.api_key
            self.server.state = FakeVastState(api_key=api_key)
            self._write_json(HTTPStatus.OK, {"ok": True})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid API key"})
            return
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._record(payload)
        endpoint_id = self._resource_id("endptjobs")
        if endpoint_id is not None:
            resource = self.server.state.endpoints.get(endpoint_id)
            if not resource:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            resource.update(payload)
            self._write_json(HTTPStatus.OK, {"result": endpoint_id})
            return
        workergroup_id = self._resource_id("workergroups")
        if workergroup_id is not None:
            resource = self.server.state.workergroups.get(workergroup_id)
            if not resource:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            resource.update(payload)
            self._write_json(HTTPStatus.OK, {"result": workergroup_id})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid API key"})
            return
        self._record()
        endpoint_id = self._resource_id("endptjobs")
        if endpoint_id is not None:
            removed = self.server.state.endpoints.pop(endpoint_id, None)
            if not removed:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._write_json(HTTPStatus.OK, {"result": endpoint_id})
            return
        workergroup_id = self._resource_id("workergroups")
        if workergroup_id is not None:
            removed = self.server.state.workergroups.pop(workergroup_id, None)
            if not removed:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._write_json(HTTPStatus.OK, {"result": workergroup_id})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})


def start_fake_vast(
    *,
    api_key: str = "test-vast-key",
    port: int = 0,
) -> tuple[FakeVastServer, threading.Thread]:
    server = FakeVastServer(("127.0.0.1", port), FakeVastState(api_key=api_key))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the no-spend Mentat Vast simulator")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--api-key", default="test-vast-key")
    parser.add_argument("--write-info", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    server = FakeVastServer(
        ("127.0.0.1", args.port),
        FakeVastState(api_key=args.api_key),
    )
    base_url = f"http://127.0.0.1:{server.server_address[1]}/api/v0"
    info = {
        "base_url": base_url,
        "bundles_url": base_url + "/bundles/",
        "api_key": args.api_key,
        "pid": None,
    }
    if args.write_info:
        args.write_info.parent.mkdir(parents=True, exist_ok=True)
        args.write_info.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
