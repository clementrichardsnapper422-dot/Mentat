#!/usr/bin/env python3
"""Deterministic, cross-platform, zero-dollar Mentat production acceptance."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
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
from mentat_broker.production import install_production_hooks  # noqa: E402
from mentat_broker.runtime_policy import install_runtime_policy_hooks  # noqa: E402
from mentat_broker.safety import install_safety_hooks  # noqa: E402

REGISTRY = ROOT / "config" / "model-registry.json"


class AcceptanceFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def request_json(
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
):
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


def read_json_response(url: str, token: str) -> dict[str, Any]:
    with request_json(url, token) as response:
        return json.loads(response.read().decode("utf-8"))


def expect_http_status(
    url: str,
    expected: int,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.read()
    require(status == expected, f"expected HTTP {expected}, received {status}")
    return {"http_status": status}


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

    def check(name: str, action: Callable[[], Any]) -> Any:
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
            return detail
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
    data_dir = ROOT / ".mentat-acceptance"
    previous_environment = {
        name: os.environ.get(name)
        for name in (
            "VAST_API_KEY",
            "MENTAT_BROKER_CLIENT_TOKEN",
            "MENTAT_BROKER_ADMIN_TOKEN",
            "MENTAT_ENDPOINT_KIMI_K2_7_CODE",
            "MENTAT_VAST_API_BASE",
            "MENTAT_VAST_BUNDLES_URL",
            "VAST_TEMPLATE_HASH",
        )
    }

    def start_broker():
        nonlocal application, broker, broker_thread
        application = broker_server.BrokerApplication(ROOT, REGISTRY, data_dir)
        handler = broker_server.make_handler(application)
        broker = broker_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        broker_thread = threading.Thread(target=broker.serve_forever, daemon=True)
        broker_thread.start()
        return f"http://127.0.0.1:{broker.server_address[1]}"

    def stop_broker(*, close_application: bool) -> None:
        nonlocal application, broker, broker_thread
        if broker is not None:
            broker.shutdown()
            broker.server_close()
            broker = None
        if broker_thread is not None:
            broker_thread.join(timeout=3)
            require(not broker_thread.is_alive(), "broker thread did not stop")
            broker_thread = None
        if close_application and application is not None:
            application.close()
            application = None

    try:
        shutil.rmtree(data_dir, ignore_errors=True)
        data_dir.mkdir(parents=True, exist_ok=True)
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
                "VAST_TEMPLATE_HASH": "fake-template",
            }
        )
        install_safety_hooks()
        install_runtime_policy_hooks()
        install_production_hooks()

        broker_base = start_broker()
        application.v1.settings.update(
            {
                "setup_complete": True,
                "privacy_mode": "remote_allowed",
                "remote_inference_enabled": True,
                "budgets": {
                    "maximum_hourly_usd": 32,
                    "maximum_session_usd": 64,
                    "maximum_daily_usd": 128,
                    "maximum_monthly_usd": 1280,
                    "maximum_retry_usd": 8,
                    "maximum_fallback_usd": 16,
                    "maximum_exploration_usd": 4,
                    "one_paid_session": True,
                },
            }
        )
        model = application.registry.get("kimi-k2.7-code")
        seed_decision = application.plan(
            {
                "prompt": "Validate the fake Vast production authority path",
                "requires_tools": True,
                "estimated_input_tokens": 2048,
                "max_hourly_usd": 32,
                "max_total_usd": 64,
            }
        )
        application.approve(
            seed_decision.id,
            {"accept_benchmark_cost": True},
        )
        application.sessions.wait_until_ready(model, timeout_seconds=10)
        application.authority.provider_ready(seed_decision, model)

        def model_discovery():
            payload = read_json_response(
                broker_base + "/v1/models",
                "acceptance-client",
            )
            require(
                [item["id"] for item in payload["data"]] == ["mentat-auto"],
                "wrong model list",
            )
            return payload

        check("broker-model-discovery", model_discovery)
        check(
            "client-auth-missing-rejected",
            lambda: expect_http_status(broker_base + "/v1/models", 401),
        )
        check(
            "client-auth-wrong-rejected",
            lambda: expect_http_status(
                broker_base + "/v1/models",
                401,
                token="wrong-client",
            ),
        )
        check(
            "admin-token-cannot-use-client-api",
            lambda: expect_http_status(
                broker_base + "/v1/models",
                401,
                token="acceptance-admin",
            ),
        )
        check(
            "client-token-cannot-use-admin-api",
            lambda: expect_http_status(
                broker_base + "/v1/status",
                401,
                token="acceptance-client",
            ),
        )
        check(
            "admin-auth-accepted",
            lambda: expect_http_status(
                broker_base + "/v1/status",
                200,
                token="acceptance-admin",
            ),
        )

        def control_status():
            payload = read_json_response(
                broker_base + "/v1/status",
                "acceptance-admin",
            )
            require(payload["target_version"] == "1.0.0", "wrong release target")
            require(
                payload["release"]["production_ready"] is False,
                "unrun live gates were manufactured",
            )
            require(
                payload["spend"]["kill_switch"] is False,
                "kill switch unexpectedly enabled",
            )
            return {
                "target_version": payload["target_version"],
                "production_ready": payload["release"]["production_ready"],
                "pending_release_evidence": len(payload["release"]["pending"]),
            }

        check("v1-control-status", control_status)

        def task_analysis():
            with request_json(
                broker_base + "/v1/analyze",
                "acceptance-admin",
                {
                    "prompt": "Deploy this repository security migration",
                    "tool_names": ["git"],
                    "repository_files": 250,
                },
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            require(payload["task_class"] == "high_risk", "task analyzer weakened risk")
            require("tools" in payload["capabilities"], "tool requirement was lost")
            return payload

        check("v1-task-analysis", task_analysis)

        def offer_discovery():
            offers = application.offers_for(model, refresh=True)
            require(
                [item.id for item in offers] == [501, 502],
                "fake offers were not filtered/sorted",
            )
            require(
                fake_vast.state.calls[-1]["path"] == "/api/v0/bundles/",
                "wrong Vast path",
            )
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
                payload["choices"][0]["message"]["content"] == "Mentat no-spend inference online",
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
            require(
                content_type.startswith("text/event-stream"),
                "stream content type was lost",
            )
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
                require(
                    expected_text in payload["error"]["message"],
                    "unexpected error response",
                )
                return {
                    "http_status": exc.code,
                    "error_type": payload["error"]["type"],
                }
            raise AcceptanceFailure("request unexpectedly succeeded")

        def malformed_failure():
            try:
                request_json(
                    broker_base + "/v1/chat/completions",
                    "acceptance-client",
                    chat_payload("[[malformed]]"),
                )
            except urllib.error.HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                error = payload.get("error")
                require(
                    isinstance(error, dict),
                    "malformed response error was not structured",
                )
                require(
                    bool(error.get("message")),
                    "malformed response error message was empty",
                )
                require(
                    bool(error.get("type")),
                    "malformed response error type was empty",
                )
                return {"http_status": exc.code, "error_type": error["type"]}
            raise AcceptanceFailure("malformed upstream response unexpectedly succeeded")

        check(
            "context-error-fails-closed",
            lambda: expected_failure(
                "[[context_error]]",
                "maximum context length",
            ),
        )
        check(
            "upstream-outage-fails-closed",
            lambda: expected_failure(
                "[[server_error]]",
                "all approved model endpoints failed",
            ),
        )
        check("malformed-upstream-fails-closed", malformed_failure)

        benchmarks = application.store.list_benchmarks(100)
        successful = [item for item in benchmarks if item.get("success")]
        failed = [item for item in benchmarks if not item.get("success")]
        check(
            "telemetry-integrity",
            lambda: (
                require(
                    len(successful) == 3,
                    f"expected 3 successful samples, found {len(successful)}",
                ),
                {"successful_runtime_samples": len(successful)},
            )[1],
        )
        check(
            "malformed-response-negative-evidence",
            lambda: (
                require(
                    any("malformed completion JSON" in str(item.get("notes")) for item in failed),
                    "malformed response was not retained as failed evidence",
                ),
                {"failed_runtime_samples": len(failed)},
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

        def broker_restart():
            nonlocal broker_base
            spend_path = application.v1.spend.path
            execution_path = application.v1.executions.path
            stop_broker(close_application=True)
            require(spend_path.exists(), "spend ledger disappeared during shutdown")
            require(
                execution_path.exists(),
                "execution ledger disappeared during shutdown",
            )
            broker_base = start_broker()
            payload = read_json_response(
                broker_base + "/v1/models",
                "acceptance-client",
            )
            status = read_json_response(
                broker_base + "/v1/status",
                "acceptance-admin",
            )
            require(payload["data"][0]["id"] == "mentat-auto", "broker did not recover")
            require(
                status["spend"]["kill_switch"] is False,
                "spend state did not reopen safely",
            )
            return {
                "recovered": True,
                "port": broker.server_address[1],
                "application_reconstructed": True,
                "store_reopened": True,
            }

        check("broker-restart-recovery", broker_restart)
    finally:
        try:
            stop_broker(close_application=True)
        finally:
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
            shutil.rmtree(data_dir, ignore_errors=True)

    passed = all(item["status"] == "passed" for item in checks)
    return {
        "schema_version": 2,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "paid_compute_used": False,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Mentat's no-spend production acceptance harness"
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="write the JSON acceptance report to this path",
    )
    args = parser.parse_args()
    try:
        report = run_acceptance()
    except Exception as exc:
        report = {
            "schema_version": 2,
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
