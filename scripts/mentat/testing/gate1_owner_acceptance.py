#!/usr/bin/env python3
"""Fail-closed, no-spend Gate 1 evidence collection for an installed Windows runtime."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import subprocess
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_ENV = {
    "VAST_API_KEY",
    "VAST_TEMPLATE_HASH",
    "MENTAT_BROKER_ADMIN_TOKEN",
    "MENTAT_BROKER_CLIENT_TOKEN",
    "MENTAT_PRIMARY_UPSTREAM_URL",
}


class GateFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise GateFailure(f"{Path(command[0]).name} exited {result.returncode}: {detail[-1200:]}")
    return result


def openclaw_command() -> list[str]:
    node = ROOT / "node" / "node.exe"
    entry = ROOT / "openclaw" / "node_modules" / "openclaw" / "openclaw.mjs"
    require(node.is_file(), f"bundled Node runtime is missing: {node}")
    require(entry.is_file(), f"bundled OpenClaw entry point is missing: {entry}")
    return [str(node), str(entry)]


def parse_json_output(output: str, label: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise GateFailure(f"{label} did not return JSON: {exc}") from exc


def validate_container_inspect(inspect: dict[str, Any], workspace: Path) -> dict[str, Any]:
    host_config = inspect.get("HostConfig") or {}
    config = inspect.get("Config") or {}
    mounts = inspect.get("Mounts") or []
    require(host_config.get("NetworkMode") == "none", "sandbox network mode is not none")
    require(host_config.get("ReadonlyRootfs") is True, "sandbox root filesystem is not read-only")
    cap_drop = {str(item).upper() for item in (host_config.get("CapDrop") or [])}
    require("ALL" in cap_drop, "sandbox does not drop all capabilities")
    security_opt = {str(item).lower() for item in (host_config.get("SecurityOpt") or [])}
    require(
        any("no-new-privileges" in item for item in security_opt),
        "sandbox does not enforce no-new-privileges",
    )
    require(str(config.get("User") or "") not in {"", "0", "root"}, "sandbox runs as root")
    environment = [str(item) for item in (config.get("Env") or [])]
    names = {item.split("=", 1)[0] for item in environment}
    leaked = sorted(FORBIDDEN_ENV & names)
    require(not leaked, f"forbidden credentials reached sandbox environment: {', '.join(leaked)}")
    socket_mounts = [
        item
        for item in mounts
        if "docker.sock" in str(item.get("Source", "")).lower()
        or "docker.sock" in str(item.get("Destination", "")).lower()
    ]
    require(not socket_mounts, "Docker socket is mounted into the tool sandbox")
    workspace_resolved = str(workspace.resolve()).lower()
    writable_mounts = [
        item
        for item in mounts
        if item.get("RW") is True and str(item.get("Source", "")).lower() != workspace_resolved
    ]
    require(not writable_mounts, "sandbox has an unexpected writable host mount")
    return {
        "container_id": str(inspect.get("Id") or "")[:12],
        "network_mode": host_config.get("NetworkMode"),
        "read_only_root": host_config.get("ReadonlyRootfs"),
        "cap_drop": sorted(cap_drop),
        "security_opt": sorted(security_opt),
        "user": config.get("User"),
        "forbidden_environment_names": leaked,
        "docker_socket_mounted": False,
        "mounts": [
            {
                "source": item.get("Source"),
                "destination": item.get("Destination"),
                "writable": item.get("RW"),
            }
            for item in mounts
        ],
    }


class ProbeState:
    def __init__(self) -> None:
        self.requests = 0


class ProbeHandler(BaseHTTPRequestHandler):
    server: "ProbeServer"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def write_json(self, status: int, value: Any) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.write_json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            return
        if self.headers.get("Authorization") != "Bearer test-gate1-key":
            self.write_json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "invalid test token"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode())
        self.server.state.requests += 1
        messages = payload.get("messages") or []
        text = "\n".join(
            str(item.get("content") or "") for item in messages if isinstance(item, dict)
        )
        nonce_match = re.search(r"\[\[sandbox_probe=([a-f0-9]{32})\]\]", text)
        has_result = any(
            isinstance(item, dict) and item.get("role") == "tool" for item in messages
        )
        if nonce_match and not has_result:
            nonce = nonce_match.group(1)
            command = (
                "umask 077; printf '%s\\n' "
                f"'{{\"schema_version\":1,\"nonce\":\"{nonce}\","
                "\"tool_execution\":\"docker\"}' "
                f"> gate1-sandbox-{nonce}.json"
            )
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_gate1_exec",
                        "type": "function",
                        "function": {
                            "name": "exec",
                            "arguments": json.dumps({"command": command}),
                        },
                    }
                ],
            }
            finish_reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "Gate 1 sandbox probe complete."}
            finish_reason = "stop"
        self.write_json(
            HTTPStatus.OK,
            {
                "id": "chatcmpl-gate1",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "fake-model",
                "choices": [
                    {"index": 0, "message": message, "finish_reason": finish_reason}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )


class ProbeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        self.state = ProbeState()
        super().__init__(("127.0.0.1", 0), ProbeHandler)


def configure(cli: list[str], env: dict[str, str], key: str, value: Any) -> None:
    run(
        cli + ["config", "set", key, json.dumps(value, separators=(",", ":")), "--strict-json"],
        env=env,
    )


def run_acceptance(report_path: Path) -> dict[str, Any]:
    started = datetime.now(UTC).isoformat()
    checks: list[dict[str, Any]] = []

    def check(name: str, action) -> Any:
        began = time.monotonic()
        try:
            detail = action()
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "duration_ms": round((time.monotonic() - began) * 1000, 2),
                    "detail": detail,
                }
            )
            return detail
        except Exception as exc:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "duration_ms": round((time.monotonic() - began) * 1000, 2),
                    "error": str(exc),
                }
            )
            raise

    require(os.name == "nt", "Gate 1 owner evidence must run on the target Windows PC")
    manifest_path = ROOT / "runtime-manifest.json"
    require(manifest_path.is_file(), "run this from the installed Mentat runtime")
    manifest = parse_json_output(manifest_path.read_text(encoding="utf-8-sig"), "runtime manifest")
    check(
        "installed-runtime",
        lambda: {
            "root": str(ROOT),
            "version": manifest.get("version"),
            "source_commit": manifest.get("source_commit"),
            "source_checkout_present": (ROOT / ".git").exists(),
        },
    )
    check(
        "docker-ready",
        lambda: {
            "server": run(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip()
        },
    )

    cli = openclaw_command()
    nonce = secrets.token_hex(16)
    evidence_root = report_path.parent / f"gate1-{nonce}"
    state_dir = evidence_root / "openclaw-state"
    workspace = evidence_root / "workspace"
    state_dir.mkdir(parents=True, exist_ok=False)
    workspace.mkdir(parents=True, exist_ok=False)
    fake = ProbeServer()
    fake_thread = threading.Thread(target=fake.serve_forever, daemon=True)
    fake_thread.start()
    env = dict(os.environ)
    for name in FORBIDDEN_ENV:
        env.pop(name, None)
    env["OPENCLAW_STATE_DIR"] = str(state_dir)
    env["OPENCLAW_CONFIG_PATH"] = str(state_dir / "openclaw.json")
    env["MENTAT_GATE1_NO_SPEND"] = "1"
    upstream = f"http://127.0.0.1:{fake.server_address[1]}/v1"
    session_key = f"agent:main:gate1-{nonce}"
    marker = workspace / f"gate1-sandbox-{nonce}.json"

    try:
        configure(
            cli,
            env,
            "models.providers.mentat-gate1",
            {
                "baseUrl": upstream,
                "apiKey": "test-gate1-key",
                "api": "openai-completions",
                "models": [
                    {
                        "id": "fake-model",
                        "name": "Mentat Gate 1 Fake",
                        "reasoning": False,
                        "input": ["text"],
                        "contextWindow": 8192,
                        "maxTokens": 1024,
                    }
                ],
            },
        )
        configure(cli, env, "agents.defaults.model.primary", "mentat-gate1/fake-model")
        configure(cli, env, "agents.defaults.workspace", str(workspace))
        configure(
            cli,
            env,
            "agents.defaults.sandbox",
            {
                "mode": "all",
                "backend": "docker",
                "scope": "session",
                "workspaceAccess": "rw",
                "docker": {
                    "network": "none",
                    "readOnlyRoot": True,
                    "capDrop": ["ALL"],
                    "securityOpt": ["no-new-privileges:true"],
                },
            },
        )
        configure(cli, env, "tools.elevated.enabled", False)

        check(
            "effective-sandbox-policy",
            lambda: parse_json_output(
                run(
                    cli + ["sandbox", "explain", "--session", session_key, "--json"],
                    env=env,
                ).stdout,
                "sandbox explain",
            ),
        )
        check(
            "actual-openclaw-tool-execution",
            lambda: {
                "session_key": session_key,
                "agent_result": parse_json_output(
                    run(
                        cli
                        + [
                            "agent",
                            "--local",
                            "--session-key",
                            session_key,
                            "--message",
                            f"[[sandbox_probe={nonce}]] Execute the requested probe exactly once.",
                            "--json",
                        ],
                        env=env,
                        timeout=180,
                    ).stdout,
                    "agent",
                ),
            },
        )
        marker_payload = check(
            "sandbox-marker",
            lambda: parse_json_output(marker.read_text(encoding="utf-8"), "sandbox marker"),
        )
        require(marker_payload.get("nonce") == nonce, "sandbox marker nonce mismatch")
        sandboxes = parse_json_output(
            run(cli + ["sandbox", "list", "--json"], env=env).stdout,
            "sandbox list",
        )
        entries = sandboxes if isinstance(sandboxes, list) else sandboxes.get("sandboxes", [])
        matching = [
            item for item in entries if session_key in json.dumps(item, separators=(",", ":"))
        ]
        require(len(matching) == 1, f"expected one sandbox for {session_key}, found {len(matching)}")
        container_id = (
            matching[0].get("containerId")
            or matching[0].get("container_id")
            or matching[0].get("id")
        )
        require(bool(container_id), "sandbox list omitted the Docker container id")
        inspect_values = parse_json_output(
            run(["docker", "inspect", str(container_id)]).stdout,
            "docker inspect",
        )
        require(
            isinstance(inspect_values, list) and len(inspect_values) == 1,
            "unexpected inspect result",
        )
        check(
            "docker-containment",
            lambda: validate_container_inspect(inspect_values[0], workspace),
        )
        require(fake.state.requests >= 2, "fake OpenAI did not complete the tool loop")
    finally:
        fake.shutdown()
        fake.server_close()
        fake_thread.join(timeout=2)
        try:
            run(
                cli + ["sandbox", "recreate", "--session", session_key, "--force"],
                env=env,
            )
        except Exception:
            pass

    return {
        "schema_version": 1,
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "machine": {"platform": platform.platform(), "hostname": platform.node()},
        "artifact": {
            "version": manifest.get("version"),
            "source_commit": manifest.get("source_commit"),
        },
        "passed": all(item["status"] == "passed" for item in checks),
        "paid_compute_used": False,
        "network_policy": "fake inference on loopback; Docker tool network disabled",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Mentat Gate 1 owner-PC evidence")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run_acceptance(args.report)
    except Exception as exc:
        report = {
            "schema_version": 1,
            "completed_at": datetime.now(UTC).isoformat(),
            "passed": False,
            "paid_compute_used": False,
            "fatal_error": str(exc),
        }
    rendered = json.dumps(report, indent=2)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
