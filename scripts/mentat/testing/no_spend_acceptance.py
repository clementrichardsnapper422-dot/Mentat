#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "services" / "model-broker"
TESTING = ROOT / "scripts" / "mentat" / "testing"
for location in (SERVICE, TESTING):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from fake_openai import start_fake_openai  # noqa: E402
from fake_vast import start_fake_vast  # noqa: E402
from mentat_broker import server as broker_server  # noqa: E402
from mentat_broker.models import Offer  # noqa: E402
from mentat_broker.production import install_production_hooks  # noqa: E402
from mentat_broker.production_app import ProductionBrokerApplication  # noqa: E402
from mentat_broker.production_http import (  # noqa: E402
    LoopbackThreadingHTTPServer,
    production_handler_factory,
)
from mentat_broker.runtime_policy import install_runtime_policy_hooks  # noqa: E402
from mentat_broker.safety import install_safety_hooks  # noqa: E402

REGISTRY = ROOT / "config" / "model-registry.json"


class AcceptanceFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def request_json(url: str, token: str, payload: dict[str, Any] | None = None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    return urllib.request.urlopen(request, timeout=10)


def chat_payload(content: str, **extra: Any) -> dict[str, Any]:
    return {
        "model": "mentat-auto",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 128,
        "stream": False,
        **extra,
    }


def run_acceptance() -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    checks: list[dict[str, Any]] = []

    def check(name: str, action) -> None:
        started = time.monotonic()
        try:
            detail = action()
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "detail": detail,
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error": str(exc),
                }
            )
            raise

    fake_vast, fake_vast_thread = start_fake_vast()
    fake_openai, fake_openai_thread = start_fake_openai()
    application = None
    broker = None
    broker_thread = None
    previous_environment = {
        name: os.environ.get(name)
        for name in (
            "VAST_API_KEY",
            "MENTAT_BROKER_CLIENT_TOKEN",
            "MENTAT_BROKER_ADMIN_TOKEN",
            "MENTAT_ENDPOINT_KIMI_K2_7_CODE",
            "MENTAT_VAST_API_BASE",
            "MENTAT_VAST_BUNDLES_URL",
        )
    }
    try:
        vast_base = f"http://127.0.0.1:{fake_vast.server_address[1]}/api/v0"
        upstream_base = f"http://127.0.0.1:{fake_openai.server_address[1]}/v1"
        os.environ.update(
            {
                "VAST_API_KEY": "test-vast-key",
                "MENTAT_BROKER_CLIENT_TOKEN": "acceptance-client",
                "MENTAT_BROKER_ADMIN_TOKEN": "acceptance-admin",
                "MENTAT_ENDPOINT_KIMI_K2_7_CODE": upstream_base,
                "MENTAT_VAST_API_BASE": vast_base,
                "MENTAT_VAST_BUNDLES_URL": vast_base + "/bundles/",
            }
        )
        install_safety_hooks()
        install_runtime_policy_hooks()
        install_production_hooks()

        data_dir = ROOT / ".mentat-acceptance"
        data_dir.mkdir(parents=True, exist_ok=True)
        database = data_dir / "broker.sqlite3"
        database.unlink(missing_ok=True)
        application = ProductionBrokerApplication(ROOT, REGISTRY, data_dir)
        model = application.registry.get("kimi-k2.7-code")
        offer = Offer(
            id=501,
            gpu_name="H200",
            num_gpus=8,
            gpu_ram_mb=141000,
            hourly_usd=24,
            reliability=0.995,
            verified=True,
            bw_nvlink=900,
            disk_space_gb=1000,
        )
        now = datetime.now(UTC)
        application.store.upsert_session(
            model.id,
            status="ready",
            endpoint_url=upstream_base,
            hourly_usd=offer.hourly_usd,
            offer=offer,
            decision_id="no-spend-approved-session",
            started_at=now.isoformat(),
            last_used_at=now.isoformat(),
            approved_until=(now + timedelta(minutes=30)).isoformat(),
        )

        handler = production_handler_factory(
            broker_server.make_handler,
            broker_server._decision_ui,
            application,
        )
        broker = LoopbackThreadingHTTPServer(("127.0.0.1", 0), handler)
        broker_thread = threading.Thread(target=broker.serve_forever, daemon=True)
        broker_thread.start()
        broker_base = f"http://127.0.0.1:{broker.server_address[1]}"

        def model_discovery():
            with request_json(broker_base + "/v1/models", "acceptance-client") as response:
                payload = json.loads(response.read().decode("utf-8"))
            require([item["id"] for item in payload["data"]] == ["mentat-auto"], "wrong model list")
            return payload

        check("broker-model-discovery", model_discovery)

        def offer_discovery():
            offers = application.offers_for(model, refresh=True)
            require([item.id for item in offers] == [501, 502], "fake offers were not filtered/sorted")
            require(fake_vast.state.calls[-1]["path"] == "/api/v0/bundles/", "wrong Vast path")
            return {"offer_ids": [item.id for item in offers]}

        check("vast-offer-discovery", offer_discovery)

        def normal_chat():
            with request_json(
                broker_base + "/v1/chat/completions",
                "acceptance-client",
                chat_payload("Explain this architecture"),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                decision_id = response.headers["X-Mentat-Decision-Id"]
            require(
                payload["choices"][0]["message"]["content"]
                == "Mentat no-spend inference online",
                "normal completion mismatch",
            )
            return {"decision_id": decision_id}

        check("json-completion", normal_chat)

        def streaming_chat():
            with request_json(
                broker_base + "/v1/chat/completions",
                "acceptance-client",
                chat_payload("[[stream]]", stream=True),
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8")
            require(content_type.startswith("text/event-stream"), "stream content type was lost")
            require("data: [DONE]" in body, "stream terminator missing")
            return {"bytes": len(body)}

        check("streaming-completion", streaming_chat)

        def tool_chat():
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "description": "Write a test value",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    },
                }
            ]
            with request_json(
                broker_base + "/v1/chat/completions",
                "acceptance-client",
                chat_payload("[[tool]]", tools=tools),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            call = payload["choices"][0]["message"]["tool_calls"][0]
            require(call["function"]["name"] == "write_file", "tool name changed")
            return {"tool": call["function"]["name"]}

        check("tool-call-compatibility", tool_chat)

        def expected_failure(content: str, expected_text: str):
            try:
                request_json(
                    broker_base + "/v1/chat/completions",
                    "acceptance-client",
                    chat_payload(content),
                )
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                require(expected_text in payload["error"]["message"], "unexpected error response")
                return {"http_status": exc.code, "error_type": payload["error"]["type"]}
            raise AcceptanceFailure("request unexpectedly succeeded")

        check(
            "context-error-fails-closed",
            lambda: expected_failure("[[context_error]]", "maximum context length"),
        )
        check(
            "upstream-outage-fails-closed",
            lambda: expected_failure("[[server_error]]", "all approved model endpoints failed"),
        )

        successful = application.store.list_benchmarks(100)
        check(
            "telemetry-integrity",
            lambda: (
                require(len(successful) == 3, f"expected 3 successful samples, found {len(successful)}"),
                {"successful_runtime_samples": len(successful)},
            )[1],
        )
        check(
            "no-real-vast-network",
            lambda: (
                require(
                    all("console.vast.ai" not in str(call) for call in fake_vast.state.calls),
                    "real Vast hostname appeared in fake call history",
                ),
                {"fake_vast_calls": len(fake_vast.state.calls)},
            )[1],
        )
    finally:
        if broker is not None:
            broker.shutdown()
            broker.server_close()
        if broker_thread is not None:
            broker_thread.join(timeout=2)
        if application is not None:
            application.close()
        fake_openai.shutdown()
        fake_openai.server_close()
        fake_openai_thread.join(timeout=2)
        fake_vast.shutdown()
        fake_vast.server_close()
        fake_vast_thread.join(timeout=2)
        for name, value in previous_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    passed = all(item["status"] == "passed" for item in checks)
    return {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "paid_compute_used": False,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Mentat's no-spend production acceptance harness")
    parser.add_argument("--report", type=Path, help="write the JSON acceptance report to this path")
    args = parser.parse_args()
    try:
        report = run_acceptance()
    except Exception as exc:
        report = {
            "schema_version": 1,
            "completed_at": datetime.now(UTC).isoformat(),
            "passed": False,
            "paid_compute_used": False,
            "fatal_error": str(exc),
        }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
